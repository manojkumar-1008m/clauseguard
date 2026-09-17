"""Micro-overfit test and mask alignment validation for Phase 4."""
from __future__ import annotations

import json
import os
import random
import sys
import torch
import torch.nn.functional as F

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.clauseguard_llm.config import ClauseGuardLLMConfig
from backend.clauseguard_llm.generation import generate_clauseguard_text
from backend.clauseguard_llm.model import ClauseGuardDecoderLM
from backend.clauseguard_llm.tokenizer import ClauseGuardTokenizer
from backend.clauseguard_llm.phase4_3_repair import build_phase4_3_corpus, serialize, _cache_rows


def test_mask_boundary_alignment():
    records = build_phase4_3_corpus(10, seed=7)
    tokenizer = ClauseGuardTokenizer(vocab_size=2048)
    tokenizer.train(serialize(r) for r in records)
    config = ClauseGuardLLMConfig(vocab_size=len(tokenizer), context_length=384)

    input_tensor, label_tensor, diagnostics = _cache_rows(records[:3], tokenizer, config)
    eos_id = tokenizer.encoder["<eos>"]
    answer_id = tokenizer.encoder["<answer>"]

    for row_idx, row in enumerate(records[:3]):
        inputs = input_tensor[row_idx].tolist()
        labels = label_tensor[row_idx].tolist()
        diag = diagnostics[row_idx]
        boundary = diag["boundary"]

        # 1. Labels before boundary must be -100 (masked)
        assert all(label == -100 for label in labels[:boundary]), f"Prompt tokens before boundary {boundary} leaked into loss"

        # 2. First active label must be at index boundary
        first_active = next(i for i, v in enumerate(labels) if v != -100)
        assert first_active == boundary, f"First active label is at {first_active}, expected boundary {boundary}"

        # 3. The input at first_active position must be <answer>
        assert inputs[first_active] == answer_id, f"Input at first_active position was {inputs[first_active]}, expected <answer> {answer_id}"

        # 4. eos must be present in the active labels
        active_labels = [l for l in labels if l != -100]
        assert eos_id in active_labels, "EOS token was not included in active answer labels"


def test_single_example_micro_overfit():
    random.seed(7)
    torch.manual_seed(7)
    records = build_phase4_3_corpus(5, seed=7)
    sample = records[0]

    tokenizer = ClauseGuardTokenizer(vocab_size=1024)
    tokenizer.train([serialize(sample)])

    config = ClauseGuardLLMConfig(
        vocab_size=len(tokenizer),
        context_length=256,
        embedding_dim=64,
        num_layers=2,
        num_heads=4,
        feedforward_dim=256,
        dropout=0.0,
        device="cpu"
    )

    input_tensor, label_tensor, _ = _cache_rows([sample], tokenizer, config)
    model = ClauseGuardDecoderLM(config)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)

    initial_loss = None
    final_loss = None
    for step in range(250):
        optimizer.zero_grad(set_to_none=True)
        logits = model(input_tensor)
        loss = F.cross_entropy(
            logits.reshape(-1, logits.size(-1)),
            label_tensor.reshape(-1),
            ignore_index=-100
        )
        if initial_loss is None:
            initial_loss = float(loss.item())
        loss.backward()
        optimizer.step()
        final_loss = float(loss.item())

    assert initial_loss is not None and final_loss is not None
    assert final_loss < 0.05, f"Single example failed to overfit: initial={initial_loss:.3f}, final={final_loss:.5f}"
    assert final_loss < initial_loss * 0.01, f"Loss did not decrease by 99%: initial={initial_loss}, final={final_loss}"

    # Greedily generate from the prompt
    prompt = serialize(sample).split("<ANSWER>", 1)[0] + "<ANSWER>"
    out = generate_clauseguard_text(
        model,
        prompt,
        tokenizer=tokenizer,
        max_new_tokens=40,
        min_new_tokens=4,
        temperature=1e-8,
        top_k=1,
        return_metadata=True
    )
    completion = out["completion_text"].strip()
    assert len(completion) > 0, "Greedy generation produced empty output"

    # Check key words from target answer are reproduced
    target_words = set(sample["answer"].lower().split())
    gen_words = set(completion.lower().split())
    overlap = target_words.intersection(gen_words)
    assert len(overlap) >= 5, f"Generated answer did not match target answer words. Gen: {completion}"
