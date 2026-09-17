from __future__ import annotations

import os
import random
import tempfile

import torch
import torch.nn.functional as F

from .config import SmokeTestConfig
from .dataset import ClauseGuardQADataset
from .model import ClauseGuardDecoderLM


def run_smoke_test(config: SmokeTestConfig | None = None, dataset: ClauseGuardQADataset | None = None, steps: int = 3, seed: int = 7):
    if config is None:
        config = SmokeTestConfig()
    if dataset is None:
        dataset = ClauseGuardQADataset(seed=seed)

    random.seed(seed)
    torch.manual_seed(seed)

    model = ClauseGuardDecoderLM(config).to(config.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)

    sample = dataset[0]
    input_ids = torch.tensor([sample["input_ids"]], dtype=torch.long, device=config.device)
    target_ids = torch.tensor([sample["target_ids"]], dtype=torch.long, device=config.device)
    input_ids = input_ids[:, : config.context_length]
    target_ids = target_ids[:, : config.context_length]

    initial_state = {name: param.detach().clone() for name, param in model.named_parameters()}

    loss_history = []
    for _ in range(steps):
        optimizer.zero_grad(set_to_none=True)
        logits = model(input_ids)
        loss = F.cross_entropy(logits.view(-1, logits.size(-1)), target_ids.view(-1), ignore_index=0)
        loss.backward()
        optimizer.step()
        loss_history.append(float(loss.item()))

    grads_nonzero = False
    for param in model.parameters():
        if param.grad is not None and torch.any(param.grad != 0):
            grads_nonzero = True
            break

    params_changed = any(
        not torch.equal(initial_state[name], param.detach())
        for name, param in model.named_parameters()
    )

    ckpt_path = os.path.join(tempfile.gettempdir(), "clauseguard_llm_smoke.pt")
    torch.save({"model_state": model.state_dict(), "config": vars(config)}, ckpt_path)
    checkpoint_saved = os.path.exists(ckpt_path)

    reloaded = ClauseGuardDecoderLM(config).to(config.device)
    reloaded.load_state_dict(torch.load(ckpt_path, map_location=config.device)["model_state"])
    reloaded.eval()

    logits = reloaded(input_ids)
    logits_valid = torch.isfinite(logits).all().item()
    generated = reloaded.generate(input_ids, max_new_tokens=4)
    generated_tokens = generated[0].tolist()
    decoded_tokens = ''.join(chr(token) if 32 <= token < 127 else ' ' for token in generated_tokens if token != 0)

    loss_finite = all(torch.isfinite(torch.tensor(loss_value)).item() for loss_value in loss_history)
    return {
        "loss_finite": loss_finite,
        "gradients_nonzero": grads_nonzero,
        "parameters_changed": params_changed,
        "checkpoint_saved": checkpoint_saved,
        "checkpoint_loaded": True,
        "logits_valid": bool(logits_valid),
        "generation_valid": bool(generated.size(1) > input_ids.size(1)),
        "decoded_tokens_valid": isinstance(decoded_tokens, str) and len(decoded_tokens.strip()) > 0,
        "decoded_text": decoded_tokens,
        "loss_values": loss_history,
        "final_loss": loss_history[-1],
    }
