from __future__ import annotations

import torch

from .config import ClauseGuardLLMConfig
from .model import ClauseGuardDecoderLM


def _apply_no_repeat_ngram(logits: torch.Tensor, generated: torch.Tensor, ngram_size: int) -> torch.Tensor:
    if ngram_size <= 0 or generated.size(1) < ngram_size - 1:
        return logits
    prefix = tuple(generated[0, -(ngram_size - 1):].tolist()) if ngram_size > 1 else tuple()
    blocked = set()
    ids = generated[0].tolist()
    for index in range(len(ids) - ngram_size + 1):
        ngram = tuple(ids[index:index + ngram_size])
        if ngram[:-1] == prefix:
            blocked.add(ngram[-1])
    if blocked:
        logits[:, list(blocked)] = float("-inf")
    return logits


def _apply_top_p(logits: torch.Tensor, top_p: float | None) -> torch.Tensor:
    if top_p is None or not 0.0 < top_p < 1.0:
        return logits
    sorted_logits, sorted_indices = torch.sort(logits, descending=True, dim=-1)
    cumulative = torch.softmax(sorted_logits, dim=-1).cumsum(dim=-1)
    remove = cumulative > top_p
    remove[:, 1:] = remove[:, :-1].clone()
    remove[:, 0] = False
    filtered = sorted_logits.masked_fill(remove, float("-inf"))
    return torch.zeros_like(logits).scatter(1, sorted_indices, filtered)


def generate_clauseguard_text(model: ClauseGuardDecoderLM, prompt: str, tokenizer=None, max_new_tokens: int = 32, temperature: float = 1.0, top_k: int | None = 20, top_p: float | None = None, min_new_tokens: int = 0, repetition_penalty: float = 1.0, no_repeat_ngram_size: int = 0, return_metadata: bool = False):
    """Generate ClauseGuard-domain text from a short prompt using the local decoder model."""
    device = next(model.parameters()).device
    if tokenizer is not None:
        prompt_ids = tokenizer.encode(prompt, add_special_tokens=False)
        token_ids = [tokenizer.encoder.get("<bos>", 0)] + prompt_ids[: max(0, model.config.context_length - 1)]
    else:
        token_ids = [ord(ch) % model.config.vocab_size for ch in prompt][: model.config.context_length]
    if not token_ids:
        token_ids = [0]
    input_tensor = torch.tensor([token_ids], dtype=torch.long, device=device)
    model.eval()
    generated = input_tensor.clone()
    with torch.no_grad():
        for step in range(max_new_tokens):
            context = generated[:, -model.config.context_length:]
            logits = model(context)[:, -1, :] / max(temperature, 1e-8)
            if repetition_penalty != 1.0:
                for token_id in set(generated[0].tolist()):
                    if logits[0, token_id] < 0:
                        logits[0, token_id] *= repetition_penalty
                    else:
                        logits[0, token_id] /= repetition_penalty
            logits = _apply_no_repeat_ngram(logits, generated, no_repeat_ngram_size)
            if tokenizer is not None and step + 1 < min_new_tokens:
                logits[:, tokenizer.encoder.get("<eos>", 0)] = float("-inf")
            if top_k is not None:
                values, _ = torch.topk(logits, min(top_k, logits.size(-1)))
                logits = logits.masked_fill(logits < values[:, -1, None], float("-inf"))
            logits = _apply_top_p(logits, top_p)
            if temperature <= 1e-4 or top_k == 1:
                next_token = torch.argmax(logits, dim=-1, keepdim=True)
            else:
                next_token = torch.multinomial(torch.softmax(logits, dim=-1), 1)
            generated = torch.cat([generated, next_token], dim=1)
            if tokenizer is not None and step + 1 >= min_new_tokens:
                token_val = int(next_token.item())
                eos_id = tokenizer.encoder.get("<eos>")
                ans_end_id = tokenizer.encoder.get("</answer>")
                if token_val == eos_id or (ans_end_id is not None and token_val == ans_end_id):
                    break
    completion_ids = generated[0, len(token_ids):].tolist()
    eos_id = tokenizer.encoder.get("<eos>") if tokenizer is not None else None
    ans_end_id = tokenizer.encoder.get("</answer>") if tokenizer is not None else None
    eos_completed = (eos_id is not None and eos_id in completion_ids) or (ans_end_id is not None and ans_end_id in completion_ids)
    if tokenizer is not None:
        text = tokenizer.decode(generated[0].tolist()).strip()
        comp_text = tokenizer.decode(completion_ids).strip()
        if "</answer>" in comp_text:
            comp_text = comp_text.split("</answer>", 1)[0].strip()
    else:
        text = "".join(chr(int(token)) if 32 <= int(token) < 127 else " " for token in generated[0].tolist()).strip()
        comp_text = text
    if return_metadata:
        return {"text": text, "completion_text": comp_text, "new_token_count": len(completion_ids), "eos_completed": eos_completed, "token_ids": generated[0].tolist()}
    return text


def generate_clauseguard_batch(model: ClauseGuardDecoderLM, prompts: list[str], tokenizer=None, **generation_kwargs) -> list[dict]:
    """Generate independently per prompt so padding cannot alter positions or logits."""
    return [generate_clauseguard_text(model, prompt, tokenizer=tokenizer, return_metadata=True, **generation_kwargs) for prompt in prompts]
