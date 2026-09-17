"""Read-only Phase 4.2 generation-failure diagnostics.

This module intentionally does not launch the full corpus training run or alter
quality gates. It produces small, reproducible diagnostics for the current
model, tokenizer, targets, and generation loop.
"""
from __future__ import annotations

import json
import random
import re
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import torch
import torch.nn.functional as F

from .config import ClauseGuardLLMConfig
from .generation import generate_clauseguard_text
from .model import ClauseGuardDecoderLM
from .phase4_1_training import _cache_payload, _fast_config
from .phase4_training import (
    _format_row,
    _output_metrics,
    add_follow_up_records,
    build_phase4_corpus,
    serialize_analysis_context,
)
from .tokenizer import ClauseGuardTokenizer


def _parameter_breakdown(model: ClauseGuardDecoderLM) -> dict[str, int]:
    groups = {"token_embedding": 0, "position_embedding": 0, "layers": 0, "final_norm": 0, "output_projection": 0}
    for name, parameter in model.named_parameters():
        count = parameter.numel()
        if name.startswith("token_embedding"):
            groups["token_embedding"] += count
        elif name.startswith("position_embedding"):
            groups["position_embedding"] += count
        elif name.startswith("layers"):
            groups["layers"] += count
        elif name.startswith("ln_f"):
            groups["final_norm"] += count
        elif name.startswith("head"):
            groups["output_projection"] += count
    groups["total"] = sum(groups.values())
    return groups


def _target_diagnostic(row: dict, tokenizer: ClauseGuardTokenizer, context_length: int) -> dict:
    text = _format_row(row)
    full_ids = tokenizer.encode(text, add_special_tokens=True)
    answer_marker = text.split("<ANSWER>", 1)[0] + "<ANSWER>"
    boundary_without_bos = len(tokenizer.encode(answer_marker, add_special_tokens=False))
    sequence = full_ids[:context_length]
    width = min(context_length, len(sequence) - 1)
    inputs = sequence[:width]
    labels = sequence[1:width + 1]
    mask = [True] * len(labels)
    for index in range(max(0, min(width, boundary_without_bos - 1))):
        mask[index] = False
    labels_for_loss = [label if contributes else -100 for label, contributes in zip(labels, mask)]
    decoded_answer_ids = [label for label, contributes in zip(labels, mask) if contributes and label not in {tokenizer.encoder["<pad>"]}]
    return {
        "raw": {"analysis_context": row["analysis_context"], "question": row["question"], "answer": row["answer"]},
        "serialized": text,
        "token_ids": full_ids,
        "input_ids": inputs,
        "label_ids": labels_for_loss,
        "loss_mask": mask,
        "answer_boundary_without_bos": boundary_without_bos,
        "answer_label_count": sum(mask),
        "eos_id": tokenizer.encoder["<eos>"],
        "eos_in_sequence": tokenizer.encoder["<eos>"] in sequence,
        "pad_labels": sum(label == tokenizer.encoder["<pad>"] for label in labels_for_loss),
        "answer_preview": tokenizer.decode(decoded_answer_ids),
    }


def _tokenizer_audit(rows: list[dict], tokenizer: ClauseGuardTokenizer) -> dict:
    texts = [_format_row(row) for row in rows]
    sequences = [tokenizer.encode(text) for text in texts]
    terms = ("subscription trap", "drip pricing", "cancellation", "renewal", "evidence", "consumer consequence", "financial exposure", "potential risk", "regulatory relevance", "unknown price")
    term_audit = {term: {"tokens": tokenizer._tokenize_text(term), "ids": tokenizer.encode(term, add_special_tokens=False), "has_unk": tokenizer.encoder["<unk>"] in tokenizer.encode(term, add_special_tokens=False)} for term in terms}
    all_ids = [token for sequence in sequences for token in sequence]
    return {
        "vocabulary_size": len(tokenizer), "special_tokens": tokenizer.special_tokens,
        "special_ids": {token: tokenizer.encoder[token] for token in tokenizer.special_tokens},
        "average_sequence_length": sum(len(sequence) for sequence in sequences) / len(sequences),
        "max_sequence_length": max(len(sequence) for sequence in sequences),
        "percentage_reaching_context": 100 * sum(len(sequence) >= 256 for sequence in sequences) / len(sequences),
        "percentage_containing_eos": 100 * sum(tokenizer.encoder["<eos>"] in sequence for sequence in sequences) / len(sequences),
        "percentage_containing_unk": 100 * sum(tokenizer.encoder["<unk>"] in sequence for sequence in sequences) / len(sequences),
        "unknown_token_rate": sum(token == tokenizer.encoder["<unk>"] for token in all_ids) / max(1, len(all_ids)),
        "terms": term_audit,
    }


def _dataset_audit(rows: list[dict], tokenizer: ClauseGuardTokenizer, sample_size: int = 100) -> dict:
    sample = rows[:sample_size]
    answers = [row["answer"].strip().lower() for row in sample]
    answer_tokens = [tokenizer.encode(row["answer"], add_special_tokens=False) for row in sample]
    sentence_shapes = [re.sub(r"\d+", "N", re.sub(r"\s+", " ", answer)).strip() for answer in answers]
    vocabulary = Counter(token for tokens in answer_tokens for token in tokens)
    grounded_markers = ("evidence", "analysis", "available", "current", "context", "risk", "pattern", "cost", "charge")
    uncertainty_markers = ("potential", "unknown", "not", "cannot", "insufficient", "qualified")
    return {
        "sample_size": len(sample), "unique_answer_count": len(set(answers)),
        "repeated_answer_count": len(answers) - len(set(answers)),
        "repeated_sentence_shape_count": len(sentence_shapes) - len(set(sentence_shapes)),
        "average_answer_tokens": sum(len(tokens) for tokens in answer_tokens) / len(answer_tokens),
        "min_answer_tokens": min(map(len, answer_tokens)), "max_answer_tokens": max(map(len, answer_tokens)),
        "answer_vocabulary_size": len(vocabulary), "template_only_rate": sum(shape.count(" ") >= 3 for shape in sentence_shapes) / len(sentence_shapes),
        "grounded_fact_rate": sum(any(marker in answer for marker in grounded_markers) for answer in answers) / len(answers),
        "uncertainty_handling_rate": sum(any(marker in answer for marker in uncertainty_markers) for answer in answers) / len(answers),
    }


def _train_micro(rows: list[dict], tokenizer: ClauseGuardTokenizer, config: ClauseGuardLLMConfig, steps: int = 300) -> tuple[ClauseGuardDecoderLM, list[float]]:
    model = ClauseGuardDecoderLM(config)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    sequences = [tokenizer.encode(_format_row(row), add_special_tokens=True)[:config.context_length] for row in rows]
    losses = []
    model.train()
    for _ in range(steps):
        width = min(config.context_length, max(len(sequence) for sequence in sequences) - 1)
        inputs = torch.tensor([sequence[:width] + [0] * (width - len(sequence[:width])) for sequence in sequences], dtype=torch.long)
        labels = torch.tensor([sequence[1:width + 1] + [-100] * (width - len(sequence[1:width + 1])) for sequence in sequences], dtype=torch.long)
        optimizer.zero_grad(set_to_none=True)
        logits = model(inputs)
        loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), labels.reshape(-1), ignore_index=-100)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.item()))
    return model, losses


def _generation_modes(model, tokenizer, row: dict) -> dict:
    prompt = f"{serialize_analysis_context(row['analysis_context'])}\n<QUESTION>\n{row['question']}\n</QUESTION>\n<ANSWER>"
    modes = {
        "greedy": {"temperature": 1e-8, "top_k": 1, "top_p": None, "repetition_penalty": 1.0, "no_repeat_ngram_size": 0},
        "sampling": {"temperature": 0.8, "top_k": None, "top_p": None, "repetition_penalty": 1.0, "no_repeat_ngram_size": 0},
        "controlled": {"temperature": 0.8, "top_k": 40, "top_p": 0.9, "repetition_penalty": 1.1, "no_repeat_ngram_size": 3},
    }
    outputs = {}
    for name, settings in modes.items():
        torch.manual_seed(7)
        outputs[name] = generate_clauseguard_text(model, prompt, tokenizer=tokenizer, max_new_tokens=24, min_new_tokens=4, return_metadata=True, **settings)
    return outputs


def run_diagnostics(output_dir: str | None = None) -> dict:
    out = Path(output_dir) if output_dir else Path(__file__).resolve().parents[2] / "artifacts" / "clauseguard_llm_v0_1_phase4_2"
    out.mkdir(parents=True, exist_ok=True)
    seed = 7
    random.seed(seed); torch.manual_seed(seed)
    corpus = add_follow_up_records(build_phase4_corpus(10000, seed), seed=seed)
    tokenizer = ClauseGuardTokenizer(vocab_size=512)
    tokenizer.train(_format_row(row) for row in corpus)
    fast_config = _fast_config()
    baseline_config = ClauseGuardLLMConfig()
    fast_model = ClauseGuardDecoderLM(fast_config)
    baseline_model = ClauseGuardDecoderLM(baseline_config)
    five = corpus[:5]
    target_rows = [_target_diagnostic(row, tokenizer, fast_config.context_length) for row in five]
    tokenizer_stats = _tokenizer_audit(corpus[:100], tokenizer)
    dataset_stats = _dataset_audit(corpus, tokenizer)
    generation = _generation_modes(fast_model, tokenizer, corpus[0])
    micro_rows = corpus[:10]
    micro_config = ClauseGuardLLMConfig(vocab_size=len(tokenizer), context_length=256, embedding_dim=64, num_layers=1, num_heads=4, feedforward_dim=256, batch_size=10, dropout=0.0, device="cpu")
    micro_model, micro_losses = _train_micro(micro_rows, tokenizer, micro_config, steps=300)
    one_model, one_losses = _train_micro(micro_rows[:1], tokenizer, micro_config, steps=400)
    exact_prompt = f"{serialize_analysis_context(micro_rows[0]['analysis_context'])}\n<QUESTION>\n{micro_rows[0]['question']}\n</QUESTION>\n<ANSWER>"
    micro_output = generate_clauseguard_text(micro_model, exact_prompt, tokenizer=tokenizer, max_new_tokens=24, min_new_tokens=4, temperature=1e-8, top_k=1, repetition_penalty=1.0, no_repeat_ngram_size=0, return_metadata=True)
    one_output = generate_clauseguard_text(one_model, exact_prompt, tokenizer=tokenizer, max_new_tokens=24, min_new_tokens=4, temperature=1e-8, top_k=1, repetition_penalty=1.0, no_repeat_ngram_size=0, return_metadata=True)
    result = {
        "status": "DIAGNOSIS COMPLETE — MULTIPLE ISSUES",
        "architecture": {"cpu_fast": {"config": asdict(fast_config), "parameters": fast_model.count_parameters(), "components": _parameter_breakdown(fast_model)}, "phase4_intended": {"config": asdict(baseline_config), "parameters": baseline_model.count_parameters(), "components": _parameter_breakdown(baseline_model)}},
        "target_diagnostics": target_rows, "tokenizer": tokenizer_stats, "dataset": dataset_stats,
        "target_audit_findings": {
            "analysis_present": all("<ANALYSIS>" in row["serialized"] and "</ANALYSIS>" in row["serialized"] for row in target_rows),
            "question_present": all("<QUESTION>" in row["serialized"] and "</QUESTION>" in row["serialized"] for row in target_rows),
            "answer_present": all("<ANSWER>" in row["serialized"] for row in target_rows),
            "answer_tokens_contribute": all(row["answer_label_count"] > 0 for row in target_rows),
            "eos_present": all(row["eos_in_sequence"] for row in target_rows),
            "padding_labels_ignored": all(row["pad_labels"] == 0 for row in target_rows),
            "mask_alignment_issue": "The current Phase 4.1 cache masks through boundary - 1; because labels are shifted, the <ANSWER> marker token is included in loss. Mask through boundary to mask the complete prompt. This is an alignment defect, not a missing-answer-target defect.",
            "causal_shift": "Inputs are sequence[t] and labels are sequence[t+1]; the decoder causal mask is lower triangular.",
        },
        "generation_modes": generation,
        "micro_overfit": {"examples": 10, "steps": 300, "initial_loss": micro_losses[0], "final_loss": micro_losses[-1], "loss_decreased": micro_losses[-1] < micro_losses[0], "greedy_output": micro_output, "expected_answer": micro_rows[0]["answer"]},
        "single_example": {"steps": 400, "initial_loss": one_losses[0], "final_loss": one_losses[-1], "loss_decreased": one_losses[-1] < one_losses[0], "greedy_output": one_output, "expected_answer": micro_rows[0]["answer"]},
        "root_cause_hypotheses": [
            "CPU_FAST intentionally reduced capacity from the six-layer Phase 4 architecture to one layer, 64 dimensions, and 512 vocabulary; this is a capacity change, not merely a performance optimization.",
            "The tokenizer treats the domain as word-level pieces with numeric fragments and does not provide subword composition; short generated cycles are visible in exact outputs.",
            "The corpus is highly templated: the sampled answer vocabulary and repeated sentence shapes should be compared with the micro-overfit result before attributing failure solely to capacity.",
            "Generation is autoregressive without KV caching and the current batched path pads prompts on the left; this affects speed/context alignment but does not by itself explain the learned repeated token cycles.",
        ],
        "recommendation": "Do not integrate /ask. First fix the shifted answer-mask boundary and remove left-padding contamination in batched generation. Then restore the intended architecture or document a deliberate smaller model, diversify the heavily templated answers, add EOS-aware answer-only training, and rerun only after a corrected micro-overfit test succeeds.",
    }
    (out / "phase4_2_diagnostics.json").write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    (out / "phase4_2_report.md").write_text("# Phase 4.2 Generation Failure Root-Cause Analysis\n\n" + json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run_diagnostics(), indent=2))