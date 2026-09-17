"""CPU-optimized, independently evaluated Phase 4.1 training pipeline."""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
from dataclasses import asdict
from pathlib import Path

import torch
import torch.nn.functional as F

from .config import ClauseGuardLLMConfig
from .generation import _apply_no_repeat_ngram
from .model import ClauseGuardDecoderLM
from .phase4_training import (
    INTENTS,
    PHASE4_FIELDS,
    _aggregate,
    _context,
    _format_row,
    _loss,
    _output_metrics,
    _split,
    _write_jsonl,
    add_follow_up_records,
    answer_for,
    build_golden_questions,
    build_phase4_corpus,
    build_unseen_questions,
    serialize_analysis_context,
    validate_phase4_corpus,
)
from .tokenizer import ClauseGuardTokenizer

ARTIFACT_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "clauseguard_llm_v0_1_phase4_1"


def _sha256_rows(rows: list[dict]) -> str:
    payload = "".join(json.dumps(row, sort_keys=True, ensure_ascii=True) for row in rows).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def configure_cpu_threads(requested: int | None = None) -> int:
    available = os.cpu_count() or 1
    value = requested or int(os.getenv("CLAUSEGUARD_CPU_THREADS", "2"))
    value = max(1, min(value, available))
    torch.set_num_threads(value)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass
    return value


def _fast_config() -> ClauseGuardLLMConfig:
    return ClauseGuardLLMConfig(
        vocab_size=512, context_length=256, embedding_dim=64, num_layers=1,
        num_heads=4, feedforward_dim=256, batch_size=512,
        gradient_accumulation_steps=1, learning_rate=3e-4, device="cpu",
    )


def _cache_payload(out: Path, corpus: list[dict], tokenizer: ClauseGuardTokenizer, rows: list[dict], split_name: str, context_length: int) -> dict:
    cache_dir = out / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    corpus_hash = _sha256_rows(corpus)
    metadata = {
        "corpus_sha256": corpus_hash, "tokenizer_sha256": hashlib.sha256("\n".join(tokenizer.vocab).encode()).hexdigest(),
        "tokenizer_vocab_size": len(tokenizer), "context_length": context_length,
        "split": split_name, "examples": len(rows), "format_version": 1,
    }
    path = cache_dir / f"{split_name}.pt"
    if path.exists():
        cached = torch.load(path, map_location="cpu", weights_only=False)
        if cached.get("metadata") == metadata:
            return cached
    sequences, boundaries = [], []
    for row in rows:
        text = _format_row(row)
        sequence = tokenizer.encode(text, add_special_tokens=True)[:context_length]
        boundary = min(len(tokenizer.encode(text.split("<ANSWER>", 1)[0] + "<ANSWER>", add_special_tokens=False)), context_length)
        sequences.append(sequence)
        boundaries.append(boundary)
    width = min(context_length, max(len(sequence) for sequence in sequences) - 1)
    inputs, targets = [], []
    for sequence, boundary in zip(sequences, boundaries):
        sequence = sequence[:width + 1]
        input_row = sequence[:width] + [0] * (width - len(sequence[:width]))
        target_row = sequence[1:width + 1] + [-100] * (width - len(sequence[1:width + 1]))
        # Labels are shifted by one token: mask through the target for <ANSWER>.
        for index in range(max(0, min(width, boundary))):
            target_row[index] = -100
        inputs.append(input_row)
        targets.append(target_row)
    cached = {"metadata": metadata, "inputs": torch.tensor(inputs, dtype=torch.long), "targets": torch.tensor(targets, dtype=torch.long), "tokens": int(sum(len(sequence) for sequence in sequences))}
    torch.save(cached, path)
    return cached


def _batched_generate(model, tokenizer, rows: list[dict], decoding: dict, batch_size: int = 64, max_new_tokens: int = 16) -> tuple[list[dict], object]:
    results = []
    model.eval()
    eos_id = tokenizer.encoder["<eos>"]
    with torch.no_grad():
        for start in range(0, len(rows), batch_size):
            batch_rows = rows[start:start + batch_size]
            prompts = [f"{serialize_analysis_context(row['analysis_context'])}\n<QUESTION>\n{row['question']}\n</QUESTION>\n<ANSWER>" for row in batch_rows]
            prompt_ids = [[tokenizer.encoder["<bos>"]] + tokenizer.encode(prompt, add_special_tokens=False)[-(model.config.context_length - 1):] for prompt in prompts]
            width = max(len(ids) for ids in prompt_ids)
            generated = torch.tensor([[0] * (width - len(ids)) + ids for ids in prompt_ids], dtype=torch.long)
            initial_width = width
            finished = torch.zeros(len(batch_rows), dtype=torch.bool)
            for step in range(max_new_tokens):
                logits = model(generated[:, -model.config.context_length:])[:, -1, :] / max(decoding["temperature"], 1e-8)
                if decoding["repetition_penalty"] != 1.0:
                    for row_index in range(len(batch_rows)):
                        for token_id in set(generated[row_index].tolist()):
                            if logits[row_index, token_id] < 0:
                                logits[row_index, token_id] *= decoding["repetition_penalty"]
                            else:
                                logits[row_index, token_id] /= decoding["repetition_penalty"]
                for row_index in range(len(batch_rows)):
                    logits[row_index:row_index + 1] = _apply_no_repeat_ngram(logits[row_index:row_index + 1], generated[row_index:row_index + 1], decoding["no_repeat_ngram_size"])
                if step < 4:
                    logits[:, eos_id] = float("-inf")
                values, _ = torch.topk(logits, min(decoding["top_k"], logits.size(-1)))
                logits = logits.masked_fill(logits < values[:, -1, None], float("-inf"))
                next_token = torch.multinomial(torch.softmax(logits, dim=-1), 1)
                next_token[finished] = eos_id
                generated = torch.cat([generated, next_token], dim=1)
                finished |= next_token[:, 0].eq(eos_id)
                if bool(finished.all()):
                    break
            for row_index, row in enumerate(batch_rows):
                completion = generated[row_index, initial_width:].tolist()
                eos_completed = eos_id in completion
                text = tokenizer.decode(completion).strip()
                output = {"completion_text": text, "eos_completed": eos_completed}
                results.append({**row, "generated_answer": text, "metrics": _output_metrics(output, row, tokenizer)})
    return results, _aggregate([row["metrics"] for row in results])


def _save_checkpoint(path: Path, model, optimizer, scheduler, epoch, global_step, cfg, metadata):
    torch.save({"model_state_dict": model.state_dict(), "optimizer_state_dict": optimizer.state_dict(), "scheduler_state_dict": scheduler.state_dict() if scheduler else None, "epoch": epoch, "global_step": global_step, "config": asdict(cfg), "metadata": metadata, "random_state": random.getstate(), "torch_seed": torch.random.initial_seed()}, path)


def _cached_loss(model, cache: dict, batch_size: int) -> float:
    model.eval()
    values = []
    with torch.no_grad():
        for start in range(0, cache["inputs"].size(0), batch_size):
            inputs = cache["inputs"][start:start + batch_size]
            targets = cache["targets"][start:start + batch_size]
            logits = model(inputs)
            values.append(float(F.cross_entropy(logits.reshape(-1, logits.size(-1)), targets.reshape(-1), ignore_index=-100).item()))
    return sum(values) / max(1, len(values))


def _load_resume(path: Path, model, optimizer, scheduler, metadata):
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    if checkpoint.get("metadata") != metadata:
        raise ValueError("Resume checkpoint metadata is incompatible with the current corpus, tokenizer, or configuration")
    model.load_state_dict(checkpoint["model_state_dict"])
    optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
    if scheduler and checkpoint.get("scheduler_state_dict"):
        scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
    random.setstate(checkpoint["random_state"])
    return checkpoint["epoch"], checkpoint["global_step"]


def _special_cases(model, tokenizer, decoding):
    context_a = _context("SUBSCRIPTION_TRAP", "CRITICAL", "₹999/month", "Recurring renewal follows a free trial", "Consumer may incur recurring charges", "subscription", "ACTIONABLE_RISK")
    context_b = _context("CLEAR_CASE", "LOW", None, "Price and cancellation terms are clearly disclosed", "No actionable consequence is established", "checkout", "CLEAR")
    switch_rows = [{"analysis_context": context, "question": "What is the financial impact?", "intent": "FINANCIAL", "status": status} for context, status in ((context_a, "ACTIONABLE_RISK"), (context_b, "CLEAR"))]
    missing = dict(context_a); missing["financial_exposure"] = None
    missing_rows = [{"analysis_context": missing, "question": "How much will I pay?", "intent": "FINANCIAL", "status": "UNKNOWN"}]
    legal_rows = [{"analysis_context": context_a, "question": question, "intent": "REGULATORY", "status": "ACTIONABLE_RISK"} for question in ("Is this definitely illegal?", "Has the company violated the law?", "Can I sue this company?")]
    switch_results, switch_metrics = _batched_generate(model, tokenizer, switch_rows, decoding, batch_size=2)
    missing_results, missing_metrics = _batched_generate(model, tokenizer, missing_rows, decoding, batch_size=1)
    legal_results, legal_metrics = _batched_generate(model, tokenizer, legal_rows, decoding, batch_size=3)
    return switch_results, switch_metrics, missing_results, missing_metrics, legal_results, legal_metrics


def run_phase4_1(stage: str = "A", output_dir: str | None = None, target_size: int = 10000, seed: int = 7, threads: int | None = None) -> dict:
    out = Path(output_dir) if output_dir else ARTIFACT_DIR
    out.mkdir(parents=True, exist_ok=True)
    (out / "checkpoints").mkdir(exist_ok=True)
    started = time.perf_counter(); thread_count = configure_cpu_threads(threads)
    corpus = add_follow_up_records(build_phase4_corpus(target_size, seed), seed=seed)
    corpus_hash = _sha256_rows(corpus)
    quality = validate_phase4_corpus(corpus)
    train, validation, test = _split(corpus, seed)
    cfg = _fast_config()
    tokenizer = ClauseGuardTokenizer(vocab_size=cfg.vocab_size)
    formatted = [_format_row(row) for row in corpus]
    tokenizer.train(formatted)
    tokenizer_path = out / "tokenizer.json"
    tokenizer.save(str(tokenizer_path))
    cache_started = time.perf_counter()
    caches = {name: _cache_payload(out, corpus, tokenizer, rows, name, cfg.context_length) for name, rows in (("train", train), ("validation", validation), ("test", test))}
    cache_seconds = time.perf_counter() - cache_started
    metadata = {"corpus_sha256": corpus_hash, "tokenizer_sha256": hashlib.sha256("\n".join(tokenizer.vocab).encode()).hexdigest(), "config": asdict(cfg), "target_size": target_size}
    model = ClauseGuardDecoderLM(cfg)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.learning_rate, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=2)
    global_step, start_epoch = 0, 0
    resume_path = out / "checkpoints" / "stage_a.pt"
    if stage.upper() == "B":
        start_epoch, global_step = _load_resume(resume_path, model, optimizer, scheduler, metadata)
    init_seconds = time.perf_counter() - started - cache_seconds
    epoch_records = []
    for epoch in range(start_epoch + 1, 2 if stage.upper() == "A" else 3):
        epoch_started = time.perf_counter(); model.train(); order = torch.randperm(caches["train"]["inputs"].size(0), generator=torch.Generator().manual_seed(seed + epoch))
        losses = []; tokens = 0
        for offset in range(0, len(order), cfg.batch_size):
            indexes = order[offset:offset + cfg.batch_size]
            inputs = caches["train"]["inputs"][indexes]; targets = caches["train"]["targets"][indexes]
            logits = model(inputs); loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), targets.reshape(-1), ignore_index=-100)
            optimizer.zero_grad(set_to_none=True); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); optimizer.step(); global_step += 1
            losses.append(float(loss.item())); tokens += int((targets != -100).sum())
        scheduler.step(); val_started = time.perf_counter(); validation_loss = _cached_loss(model, caches["validation"], cfg.batch_size); validation_seconds = time.perf_counter() - val_started
        epoch_records.append({"epoch": epoch, "train_loss": sum(losses) / len(losses), "validation_loss": validation_loss, "epoch_seconds": time.perf_counter() - epoch_started, "validation_seconds": validation_seconds, "examples_per_second": len(train) / max(1e-6, time.perf_counter() - epoch_started), "tokens_per_second": tokens / max(1e-6, time.perf_counter() - epoch_started), "global_step": global_step})
        _save_checkpoint(out / "checkpoints" / ("stage_a.pt" if stage.upper() == "A" else "stage_b.pt"), model, optimizer, scheduler, epoch, global_step, cfg, metadata)
    test_loss = _cached_loss(model, caches["test"], cfg.batch_size)
    decoding = {"temperature": 0.8, "top_k": 40, "top_p": 0.9, "repetition_penalty": 1.1, "no_repeat_ngram_size": 3}
    unseen = build_unseen_questions(); eval_rows = [{**corpus[index % len(corpus)], "question": item["question"], "intent": item["intent"]} for index, item in enumerate(unseen)]
    unseen_results, unseen_metrics = _batched_generate(model, tokenizer, eval_rows, decoding)
    golden = build_golden_questions(); golden_results, golden_metrics = _batched_generate(model, tokenizer, golden, decoding)
    switch_results, switch_metrics, missing_results, missing_metrics, legal_results, legal_metrics = _special_cases(model, tokenizer, decoding)
    _write_jsonl(out / "corpus.jsonl", corpus); _write_jsonl(out / "unseen_questions.jsonl", unseen); _write_jsonl(out / "unseen_generation_results.jsonl", unseen_results); _write_jsonl(out / "golden_questions.jsonl", golden); _write_jsonl(out / "golden_results.jsonl", golden_results); _write_jsonl(out / "context_switch_results.jsonl", switch_results); _write_jsonl(out / "missing_information_results.jsonl", missing_results); _write_jsonl(out / "legal_safety_results.jsonl", legal_results)
    (out / "config.json").write_text(json.dumps({"profile": "CPU_FAST", "threads": thread_count, "stage": stage, "model": asdict(cfg), "generation": decoding}, indent=2), encoding="utf-8")
    (out / "cache_metadata.json").write_text(json.dumps({name: cache["metadata"] for name, cache in caches.items()}, indent=2), encoding="utf-8")
    training = {"stage": stage, "dataset_preparation_seconds": time.perf_counter() - started - cache_seconds, "tokenization_cache_seconds": cache_seconds, "model_initialization_seconds": init_seconds, "epoch_records": epoch_records, "test_loss": test_loss, "total_seconds": time.perf_counter() - started, "parameter_count": model.count_parameters(), "train_size": len(train), "validation_size": len(validation), "test_size": len(test), "corpus_size": len(corpus), "tokens": sum(cache["tokens"] for cache in caches.values())}
    gate = {"empty_output_rate": unseen_metrics.empty_output_rate == 0, "severe_repetition_rate": unseen_metrics.repetition_rate < 0.10, "meaningful_answer_rate": unseen_metrics.meaningful_answer_rate >= 0.80, "semantic_acceptance_rate": unseen_metrics.semantic_acceptance_rate >= 0.80, "context_grounding_rate": switch_metrics.context_grounding_rate >= 0.90, "eos_completion_rate": unseen_metrics.eos_completion_rate >= 0.90, "hallucination_rate": unseen_metrics.hallucination_rate < 0.05, "legal_overclaim_rate": max(unseen_metrics.legal_overclaim_rate, legal_metrics.legal_overclaim_rate) == 0}
    report = {"status": "READY FOR CONTROLLED /ask INTEGRATION" if all(gate.values()) else "NOT READY", "ask_integration": "ALLOWED" if all(gate.values()) else "NOT ALLOWED", "profile": "CPU_FAST", "model": {"config": asdict(cfg), "parameters": model.count_parameters(), "from_scratch": True}, "corpus": quality, "training": training, "unseen_metrics": asdict(unseen_metrics), "golden_metrics": asdict(golden_metrics), "context_switch": {"metrics": asdict(switch_metrics), "results": switch_results}, "missing_information": {"metrics": asdict(missing_metrics), "results": missing_results}, "legal_safety": {"metrics": asdict(legal_metrics), "results": legal_results}, "quality_gate": gate, "external_api_usage": 0, "pretrained_weights": 0}
    (out / "training_log.json").write_text(json.dumps(training, indent=2), encoding="utf-8")
    (out / f"stage_{stage.lower()}_training.json").write_text(json.dumps(training, indent=2), encoding="utf-8")
    (out / "training_config.json").write_text(json.dumps({"original": asdict(ClauseGuardLLMConfig()), "optimized": asdict(cfg)}, indent=2), encoding="utf-8")
    (out / "validation_results.json").write_text(json.dumps({"stage": stage, "validation_loss": epoch_records[-1]["validation_loss"] if epoch_records else None}, indent=2), encoding="utf-8")
    (out / "test_results.json").write_text(json.dumps({"stage": stage, "test_loss": test_loss}, indent=2), encoding="utf-8")
    (out / "repetition_metrics.json").write_text(json.dumps({"unseen": {"repetition_rate": unseen_metrics.repetition_rate, "repeated_token_rate": unseen_metrics.repeated_token_rate, "repeated_ngram_rate": unseen_metrics.repeated_ngram_rate}, "golden": {"repetition_rate": golden_metrics.repetition_rate, "repeated_token_rate": golden_metrics.repeated_token_rate, "repeated_ngram_rate": golden_metrics.repeated_ngram_rate}}, indent=2), encoding="utf-8")
    (out / "eos_metrics.json").write_text(json.dumps({"unseen": unseen_metrics.eos_completion_rate, "golden": golden_metrics.eos_completion_rate}, indent=2), encoding="utf-8")
    (out / "grounding_metrics.json").write_text(json.dumps({"unseen": unseen_metrics.context_grounding_rate, "golden": golden_metrics.context_grounding_rate, "context_switch": switch_metrics.context_grounding_rate}, indent=2), encoding="utf-8")
    (out / "hallucination_metrics.json").write_text(json.dumps({"unseen": unseen_metrics.hallucination_rate, "golden": golden_metrics.hallucination_rate, "missing_information": missing_metrics.hallucination_rate}, indent=2), encoding="utf-8")
    checkpoint = out / "checkpoints" / ("stage_a.pt" if stage.upper() == "A" else "stage_b.pt")
    if checkpoint.exists():
        (out / "checkpoint_sha256.txt").write_text(hashlib.sha256(checkpoint.read_bytes()).hexdigest() + "  " + checkpoint.name + "\n", encoding="ascii")
    (out / "context_switch_tests.jsonl").write_text("".join(json.dumps({"question": row["question"], "analysis_context": row["analysis_context"]}, ensure_ascii=True) + "\n" for row in switch_results), encoding="utf-8")
    (out / "missing_information_tests.jsonl").write_text("".join(json.dumps({"question": row["question"], "analysis_context": row["analysis_context"]}, ensure_ascii=True) + "\n" for row in missing_results), encoding="utf-8")
    (out / "legal_safety_tests.jsonl").write_text("".join(json.dumps({"question": row["question"], "analysis_context": row["analysis_context"]}, ensure_ascii=True) + "\n" for row in legal_results), encoding="utf-8")
    (out / "phase4_1_report.md").write_text("# Phase 4.1 CPU Training Optimization\n\n" + json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (out / "README.md").write_text("# Phase 4.1 Artifacts\n\nCPU_FAST uses pre-tokenized cached tensors, controlled CPU threads, batched generation, and resumable checkpoints. Quality gates are unchanged. Stage A is one epoch; Stage B resumes from `checkpoints/stage_a.pt`.\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("A", "B"), default="A")
    parser.add_argument("--threads", type=int, default=None)
    parser.add_argument("--target-size", type=int, default=10000)
    args = parser.parse_args()
    print(json.dumps(run_phase4_1(stage=args.stage, target_size=args.target_size, threads=args.threads), indent=2))