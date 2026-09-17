from __future__ import annotations

import csv
import json
import random
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import torch
import torch.nn.functional as F

from .config import ClauseGuardLLMConfig
from .generation import generate_clauseguard_text
from .model import ClauseGuardDecoderLM
from .tokenizer import ClauseGuardTokenizer


PATTERN_KNOWLEDGE = {
    "SOCIAL_PROOF": {
        "label": "social proof",
        "signals": ["customer activity", "purchase counts", "reviews or ratings", "trending labels"],
        "effect": "can add social pressure and make independent evaluation harder",
        "check": "whether the activity is relevant, current, and presented with enough context",
    },
    "SCARCITY": {
        "label": "scarcity",
        "signals": ["limited stock claims", "only a few items remaining", "availability warnings"],
        "effect": "can pressure a faster decision when availability is not independently clear",
        "check": "whether the availability claim is specific, current, and material to the decision",
    },
    "FALSE_URGENCY": {
        "label": "false urgency",
        "signals": ["countdown timers", "hurry messages", "offers ending soon"],
        "effect": "can reduce time for informed comparison",
        "check": "whether the deadline is real, specific, and consistently applied",
    },
    "SUBSCRIPTION_TRAP": {
        "label": "subscription trap",
        "signals": ["trial conversion", "recurring billing", "de-emphasized renewal terms"],
        "effect": "can make recurring commitment or later charges less noticeable",
        "check": "trial duration, renewal price, recurring frequency, and cancellation steps",
    },
    "DRIP_PRICING": {
        "label": "drip pricing",
        "signals": ["additional charges", "late-disclosed fees", "post-action price changes"],
        "effect": "can make the final cost less clear during the purchase journey",
        "check": "whether mandatory charges are shown before commitment and included in the total",
    },
    "BASKET_SNAKING": {
        "label": "basket snaking",
        "signals": ["preselected extras", "added products", "unrequested options in the basket"],
        "effect": "can change the basket without an equally prominent affirmative choice",
        "check": "every basket item, quantity, and whether each addition was explicitly requested",
    },
    "FORCED_ACTION": {
        "label": "forced action",
        "signals": ["required registration", "mandatory consent", "blocked continuation"],
        "effect": "can limit the ability to complete a task without an unrelated action",
        "check": "which action is required and whether a less intrusive path is available",
    },
    "CONFIRM_SHAMING": {
        "label": "confirm shaming",
        "signals": ["guilt-based opt-out wording", "insulting decline labels", "shaming alternatives"],
        "effect": "can make refusal feel socially costly rather than neutral",
        "check": "whether accept and decline choices are equally clear and respectful",
    },
    "OBSTRUCTION": {
        "label": "obstruction",
        "signals": ["extra cancellation steps", "retention loops", "hard-to-find controls"],
        "effect": "can increase friction when a user tries to leave or undo an action",
        "check": "number of steps, available routes, and whether the exit path is comparable to entry",
    },
    "MISDIRECTION": {
        "label": "misdirection",
        "signals": ["visual emphasis on one choice", "unclear secondary actions", "distracting copy"],
        "effect": "can draw attention away from a relevant cost, term, or alternative",
        "check": "whether important information and alternatives are visible and understandable",
    },
}

QUESTION_VARIANTS = [
    "What is {label}?",
    "What does {label} mean here?",
    "Why might this be considered {label}?",
    "Why did ClauseGuard identify {label}?",
    "What about this page looks like {label}?",
    "How could {label} affect my decision?",
    "Can you explain {label} in simple words?",
    "Is this definitely {label}?",
    "What should I check when I see {label}?",
    "Why should I be careful about {label}?",
]

GENERAL_QUESTIONS = [
    ("evidence", "What evidence supports the finding?", "The answer depends on the current evidence records. Review the cited text, source, strength, provenance, and journey context; a pattern label alone is not proof."),
    ("evidence", "What does the evidence mean?", "Evidence is an observed or verified signal with provenance. It supports an assessment only to the extent that its strength, context, and consistency justify it."),
    ("consequences", "How can this affect me?", "A possible consequence is reduced clarity, choice, or control during the journey. The actual consequence depends on the current evidence and should not be invented."),
    ("price", "Could this cost me more?", "Check the displayed total, additional charges, recurring amounts, trial conversion, and when each amount was disclosed. No price should be inferred when the current analysis does not contain one."),
    ("price", "What should I check before buying?", "Check the full price, mandatory fees, renewal terms, cancellation route, basket contents, and whether urgency or pressure limits an informed choice."),
    ("renewal", "What should I check about renewal?", "Check whether a trial converts automatically, the renewal amount and frequency, when those terms appear, and whether cancellation is clear before commitment."),
    ("cancellation", "Why is cancellation difficult?", "Cancellation may be obstructed when extra steps, retention loops, or unclear controls make exit materially harder than entry. Confirm the current journey evidence."),
    ("journey", "Where in the user journey does this matter?", "Interpret the signal in its journey stage, route, and sequence. Checkout, subscription, and cancellation context can change what the same text means."),
    ("recommendations", "What should I do next?", "Review the cited evidence, verify the total and terms, inspect the basket, and pause if an important choice or cost is unclear."),
    ("certainty", "Is this definitely a dark pattern?", "No. A ClauseGuard assessment can identify a potential or supported signal based on available evidence; it does not establish a definitive legal conclusion."),
    ("certainty", "Why does ClauseGuard say potential?", "Potential means the available signals are relevant but do not meet the evidence threshold for a stronger supported assessment. More context may change the result."),
    ("certainty", "What does supported mean?", "Supported means the current evidence meets the applicable ClauseGuard support conditions. It still describes an analytical assessment, not a legal ruling."),
    ("status", "What does not supported mean?", "Not supported means the available evidence does not justify the proposed finding. It is not a claim that every related behavior is absent."),
    ("status", "What does unknown mean?", "Unknown means the current context is insufficient to make a reliable assessment. ClauseGuard should avoid filling missing facts with assumptions."),
    ("regulatory", "Does this prove a legal violation?", "No. A ClauseGuard signal or regulatory context can indicate an issue worth reviewing, but it is not legal advice or a definitive legal conclusion."),
    ("regulatory", "What is the regulatory context?", "Regulatory context explains why a finding may deserve review under applicable rules. Relevance and support depend on the jurisdiction and the evidence available."),
    ("risk", "What does the risk level mean?", "The canonical risk result is a bounded assessment based on fused evidence and consumer consequences. It should be read with the supporting evidence and certainty status."),
    ("risk", "Why should I be careful?", "Be careful when a page combines pressure, unclear costs, reduced choice, or difficult exit. Check the evidence before treating the signal as conclusive."),
    ("unknown", "What if the page context is missing?", "The answer should remain unknown or qualified. Ask for the missing journey, price, evidence, or page context instead of treating an isolated phrase as decisive."),
]


@dataclass
class CorpusSplits:
    train: list[dict]
    validation: list[dict]
    test: list[dict]


@dataclass
class Phase2RunResult:
    corpus_size: int
    train_size: int
    validation_size: int
    test_size: int
    vocabulary_size: int
    unknown_token_rate: float
    parameter_count: int
    epochs: int
    train_loss: float
    validation_loss: float
    test_loss: float
    duration_seconds: float
    generation_checks: dict
    checkpoint_paths: dict


def _answer_for_pattern(info: dict, status: str, evidence: str | None = None, variation: int = 0) -> str:
    evidence_clause = f" The current evidence is: {evidence}." if evidence else ""
    variation_closings = [
        " Use the available context before making a stronger claim.",
        " The conclusion should stay proportional to the evidence.",
        " This is a consumer-risk explanation, not a legal ruling.",
        " Missing context should remain explicit rather than guessed.",
        " Compare the signal with the complete journey and terms.",
    ]
    closing = variation_closings[variation % len(variation_closings)]
    if status == "NOT_SUPPORTED":
        return f"This text alone does not support a {info['label']} finding. The signal is not enough without relevant context and evidence.{closing}{evidence_clause}"
    if status == "UNKNOWN":
        return f"It is unknown whether this is {info['label']} because the available context is incomplete. Do not infer a finding from the label alone.{closing}{evidence_clause}"
    if status == "CLEAR":
        return f"The page clearly presents a {info['label']} signal when it uses {info['signals'][0]}. That describes the observed design, not a legal conclusion.{closing}{evidence_clause}"
    if status == "ACTIONABLE_RISK":
        return f"This may be an actionable consumer risk: {info['label']} {info['effect']}. Check {info['check']}.{closing}{evidence_clause}"
    if status == "SUPPORTED":
        return f"The available evidence supports a {info['label']} assessment because it shows {info['signals'][0]}. It remains an analytical assessment, not a definitive legal conclusion.{closing}{evidence_clause}"
    return f"ClauseGuard sees a potential {info['label']} signal. It {info['effect']}. Check {info['check']} before drawing a stronger conclusion.{closing}{evidence_clause}"


def _read_observed_rows(data_path: Path, limit: int = 500) -> list[dict]:
    rows: list[dict] = []
    if not data_path.exists():
        return rows
    with open(data_path, "r", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            pattern = (row.get("pattern_category") or "").strip().upper().replace(" ", "_")
            text = (row.get("text") or "").strip()
            if pattern in PATTERN_KNOWLEDGE and text:
                rows.append({
                    "analysis": f"Observed ClauseGuard dataset text in an ecommerce journey: {text}",
                    "question": "What does this observed text suggest?",
                    "answer": _answer_for_pattern(PATTERN_KNOWLEDGE[pattern], "POTENTIAL", text[:180]),
                    "domain": pattern,
                    "status": "POTENTIAL",
                    "provenance": "observed_dataset",
                    "family": f"observed:{row.get('sample_id', len(rows))}",
                })
            if len(rows) >= limit:
                break
    return rows


def build_phase2_corpus(data_path: str | None = None, target_size: int = 3000, seed: int = 7) -> list[dict]:
    """Build a balanced, ClauseGuard-only corpus with explicit provenance metadata."""
    rng = random.Random(seed)
    examples: list[dict] = []
    observed = _read_observed_rows(Path(data_path) if data_path else Path(__file__).resolve().parents[2] / "data" / "train_v3.csv")
    examples.extend(observed[: min(len(observed), target_size // 5)])
    statuses = ["NOT_SUPPORTED", "POTENTIAL", "SUPPORTED", "ACTIONABLE_RISK", "CLEAR", "UNKNOWN"]
    pattern_items = list(PATTERN_KNOWLEDGE.items())
    index = 0
    while len(examples) < target_size:
        pattern, info = pattern_items[index % len(pattern_items)]
        cycle = index // len(pattern_items)
        status = statuses[(cycle // len(QUESTION_VARIANTS)) % len(statuses)]
        question_template = QUESTION_VARIANTS[cycle % len(QUESTION_VARIANTS)]
        variation = (cycle // (len(QUESTION_VARIANTS) * len(statuses))) % 5
        question = question_template.format(label=info["label"])
        if variation % 3 == 1:
            question = question.replace("this", "the checkout page")
        elif variation % 3 == 2:
            question = question.replace("What", "Could you explain what")
        signal = info["signals"][variation % len(info["signals"])]
        analysis = f"Synthetic ClauseGuard analysis context {variation}: a {info['label']} concept is being reviewed. A permitted example signal is {signal}. Status under review: {status}."
        examples.append({
            "analysis": analysis,
            "question": question,
            "answer": _answer_for_pattern(info, status, variation=variation),
            "domain": pattern,
            "status": status,
            "provenance": "synthetic_canonical",
            "family": f"concept:{pattern}:block:{variation}",
        })
        index += 1

    rng.shuffle(examples)
    return examples[:target_size]


def split_phase2_corpus(corpus: list[dict], seed: int = 7) -> CorpusSplits:
    """Split by semantic family so near-duplicate wording cannot cross partitions."""
    families: dict[str, list[dict]] = {}
    for row in corpus:
        families.setdefault(row["family"], []).append(row)
    family_names = list(families)
    random.Random(seed).shuffle(family_names)
    train: list[dict] = []
    validation: list[dict] = []
    test: list[dict] = []
    for index, family in enumerate(family_names):
        target = test if index % 10 == 0 else validation if index % 10 == 1 else train
        target.extend(families[family])
    return CorpusSplits(train=train, validation=validation, test=test)


def _format_row(row: dict) -> str:
    return f"analysis: {row['analysis']} question: {row['question']} answer: {row['answer']}"


def _tokenize_rows(tokenizer: ClauseGuardTokenizer, rows: Iterable[dict], context_length: int) -> list[list[int]]:
    sequences = []
    for row in rows:
        ids = tokenizer.encode(_format_row(row), add_special_tokens=True)[:context_length]
        if len(ids) >= 3:
            sequences.append(ids)
    return sequences


def _loss_for_sequences(model: ClauseGuardDecoderLM, sequences: list[list[int]], batch_size: int, device: str) -> float:
    if not sequences:
        return float("nan")
    model.eval()
    losses = []
    with torch.no_grad():
        for start in range(0, len(sequences), batch_size):
            batch = sequences[start:start + batch_size]
            width = min(model.config.context_length, max(len(seq) for seq in batch) - 1)
            inputs = [seq[:width] + [0] * (width - len(seq[:width])) for seq in batch]
            targets = [seq[1:width + 1] + [0] * (width - len(seq[1:width + 1])) for seq in batch]
            input_tensor = torch.tensor(inputs, dtype=torch.long, device=device)
            target_tensor = torch.tensor(targets, dtype=torch.long, device=device)
            logits = model(input_tensor)
            losses.append(float(F.cross_entropy(logits.reshape(-1, logits.size(-1)), target_tensor.reshape(-1), ignore_index=0).item()))
    return sum(losses) / len(losses)


def _generation_checks(model: ClauseGuardDecoderLM, tokenizer: ClauseGuardTokenizer, questions: list[str]) -> dict:
    outputs = []
    for question in questions:
        output = generate_clauseguard_text(model, question, tokenizer=tokenizer, max_new_tokens=40, temperature=0.9, top_k=40, top_p=0.92, min_new_tokens=8)
        normalized = " ".join(output.lower().split())
        words = normalized.split()
        repeated = any(len(words) >= 5 and words[index] == words[index - 1] == words[index - 2] == words[index - 3] == words[index - 4] for index in range(4, len(words)))
        repeated = repeated or any(len(words) >= 6 and words[index:index + 3] == words[index + 3:index + 6] for index in range(len(words) - 5))
        outputs.append({"question": question, "raw_output": output, "empty": not bool(normalized), "repetitive": repeated, "token_count": len(tokenizer.encode(output, add_special_tokens=False))})
    return {"outputs": outputs, "empty_count": sum(item["empty"] for item in outputs), "repetitive_count": sum(item["repetitive"] for item in outputs)}


def train_phase2(
    config: ClauseGuardLLMConfig | None = None,
    corpus: list[dict] | None = None,
    epochs: int = 2,
    output_dir: str | None = None,
    seed: int = 7,
) -> tuple[Phase2RunResult, ClauseGuardDecoderLM, ClauseGuardTokenizer, CorpusSplits]:
    cfg = config or ClauseGuardLLMConfig()
    random.seed(seed)
    torch.manual_seed(seed)
    all_rows = corpus or build_phase2_corpus(seed=seed)
    splits = split_phase2_corpus(all_rows, seed=seed)
    tokenizer = ClauseGuardTokenizer(vocab_size=cfg.vocab_size)
    tokenizer.train(_format_row(row) for row in all_rows)
    train_sequences = _tokenize_rows(tokenizer, splits.train, cfg.context_length)
    validation_sequences = _tokenize_rows(tokenizer, splits.validation, cfg.context_length)
    test_sequences = _tokenize_rows(tokenizer, splits.test, cfg.context_length)
    model = ClauseGuardDecoderLM(cfg).to(cfg.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.learning_rate)
    start = time.perf_counter()
    last_train_loss = float("nan")
    for _ in range(epochs):
        model.train()
        random.shuffle(train_sequences)
        epoch_losses = []
        optimizer.zero_grad(set_to_none=True)
        for offset in range(0, len(train_sequences), cfg.batch_size):
            batch = train_sequences[offset:offset + cfg.batch_size]
            width = min(cfg.context_length, max(len(seq) for seq in batch) - 1)
            inputs = torch.tensor([seq[:width] + [0] * (width - len(seq[:width])) for seq in batch], dtype=torch.long, device=cfg.device)
            targets = torch.tensor([seq[1:width + 1] + [0] * (width - len(seq[1:width + 1])) for seq in batch], dtype=torch.long, device=cfg.device)
            logits = model(inputs)
            loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), targets.reshape(-1), ignore_index=0)
            (loss / max(1, cfg.gradient_accumulation_steps)).backward()
            should_step = ((offset // cfg.batch_size + 1) % max(1, cfg.gradient_accumulation_steps) == 0) or offset + cfg.batch_size >= len(train_sequences)
            if should_step:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
            epoch_losses.append(float(loss.item()))
        last_train_loss = sum(epoch_losses) / len(epoch_losses)
    duration = time.perf_counter() - start
    validation_loss = _loss_for_sequences(model, validation_sequences, cfg.batch_size, cfg.device)
    test_loss = _loss_for_sequences(model, test_sequences, cfg.batch_size, cfg.device)
    output_path = Path(output_dir) if output_dir else Path(__file__).resolve().parents[2] / "artifacts" / "clauseguard_llm_v0_1_phase2"
    output_path.mkdir(parents=True, exist_ok=True)
    latest_path = output_path / "latest.pt"
    best_path = output_path / "best.pt"
    tokenizer_path = output_path / "tokenizer.json"
    config_path = output_path / "config.json"
    torch.save({"model_state_dict": model.state_dict(), "config": asdict(cfg), "validation_loss": validation_loss}, latest_path)
    torch.save({"model_state_dict": model.state_dict(), "config": asdict(cfg), "validation_loss": validation_loss}, best_path)
    tokenizer.save(str(tokenizer_path))
    config_path.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    questions = [
        "What is social proof?", "Why did ClauseGuard flag this?", "What evidence supports the finding?",
        "How can this affect me?", "Could this cost me more?", "What should I check before buying?",
        "Is this definitely a dark pattern?", "What does the evidence mean?", "Why should I be careful?",
        "Explain this in simple words.", "What happens if I cancel the subscription?",
    ]
    checks = _generation_checks(model, tokenizer, questions)
    unknown_token_rate = tokenizer.unknown_token_rate(_format_row(row) for row in all_rows)
    metadata = {
        "corpus_size": len(all_rows), "train_size": len(splits.train), "validation_size": len(splits.validation), "test_size": len(splits.test),
        "vocabulary_size": len(tokenizer), "unknown_token_rate": unknown_token_rate, "parameter_count": model.count_parameters(), "epochs": epochs,
        "train_loss": last_train_loss, "validation_loss": validation_loss, "test_loss": test_loss, "duration_seconds": duration,
        "generation_checks": checks, "provenance_counts": dict(Counter(row["provenance"] for row in all_rows)),
    }
    (output_path / "training_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    report_lines = [
        "# ClauseGuard LLM v0.1 Phase 2 Report",
        "",
        "## Run metrics",
        f"- Corpus: {len(all_rows)} records ({metadata['provenance_counts']})",
        f"- Splits: train={len(splits.train)}, validation={len(splits.validation)}, test={len(splits.test)}",
        f"- Vocabulary: {len(tokenizer)}; unknown-token rate: {unknown_token_rate:.6f}",
        f"- Parameters: {model.count_parameters()}",
        f"- Configuration: {cfg.num_layers} layers, {cfg.embedding_dim} dimensions, {cfg.num_heads} heads, context {cfg.context_length}, batch {cfg.batch_size}, accumulation {cfg.gradient_accumulation_steps}",
        f"- Epochs: {epochs}; train loss: {last_train_loss:.6f}; validation loss: {validation_loss:.6f}; test loss: {test_loss:.6f}",
        f"- Training duration: {duration:.3f} seconds; device: {cfg.device}; torch threads: {torch.get_num_threads()}",
        "",
        "## Raw locked generation outputs",
    ]
    for item in checks["outputs"]:
        report_lines.append(f"- Q: {item['question']} | raw: {item['raw_output']} | empty={item['empty']} | repetitive={item['repetitive']}")
    report_lines.extend([
        "",
        "## Interpretation",
        f"- Empty outputs: {checks['empty_count']}; repetitive outputs: {checks['repetitive_count']}.",
        "- These outputs are raw tokenizer-decoded model output and were not replaced with templates.",
        "- This checkpoint is not ready for /ask integration: generation is incomplete or degenerate on the locked questions.",
        "- The existing risk engine and production Ask behavior were not changed by this Phase 2 pipeline.",
    ])
    (output_path / "phase2_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    result = Phase2RunResult(len(all_rows), len(splits.train), len(splits.validation), len(splits.test), len(tokenizer), unknown_token_rate, model.count_parameters(), epochs, last_train_loss, validation_loss, test_loss, duration, checks, {"latest": str(latest_path), "best": str(best_path), "tokenizer": str(tokenizer_path), "metadata": str(output_path / "training_metadata.json"), "report": str(output_path / "phase2_report.md")})
    return result, model, tokenizer, splits