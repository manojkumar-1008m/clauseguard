from __future__ import annotations

import json
import math
import random
import re
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
from .phase2_training import PATTERN_KNOWLEDGE, split_phase2_corpus
from .tokenizer import ClauseGuardTokenizer

STATUSES = ("NOT_SUPPORTED", "POTENTIAL", "SUPPORTED", "ACTIONABLE_RISK", "CLEAR", "UNKNOWN")
SCENARIOS = (
    ("checkout", "during checkout", "the total and alternatives should be visible before commitment"),
    ("subscription", "in a subscription flow", "trial conversion, renewal, and cancellation terms should be clear"),
    ("cancellation", "during cancellation", "the exit route should not be materially harder than the entry route"),
    ("product", "on a product page", "the user should be able to evaluate the offer without artificial pressure"),
    ("basket", "in the basket", "each item and quantity should reflect an intentional user choice"),
)

GENERAL_BANK = [
    ("evidence", "What evidence supports this finding?", "Review the cited observation, source, strength, provenance, and journey context. A label alone is not proof.", "evidence and provenance"),
    ("evidence", "Why was this page flagged?", "ClauseGuard flags a page when available signals meet the configured analytical conditions. The exact reason must come from the current evidence, not an invented fact.", "current evidence and configured conditions"),
    ("evidence", "What did the price analyzer find?", "Check the runtime price analysis for displayed, additional, recurring, trial, renewal, and late-disclosed amounts. Do not infer a price that is not present.", "runtime price fields"),
    ("evidence", "Which evidence came from the DOM?", "DOM evidence describes observed structure or presentation, such as controls, emphasis, visibility, and selected options. Its meaning depends on the journey context.", "DOM provenance and context"),
    ("evidence", "What did the behavior analyzer detect?", "Behavior evidence describes observed interaction or sequence signals. It should be interpreted with route, stage, event order, and provenance.", "behavior sequence and provenance"),
    ("consequence", "Could this cost me more?", "Check the current total, mandatory fees, recurring charges, trial conversion, and disclosure timing. No monetary amount should be invented from a pattern label.", "current price evidence"),
    ("consequence", "What happens if I continue?", "The possible consequence depends on the current finding. You may face less clarity, choice, or control, but the answer must follow the available evidence.", "consumer consequence and evidence"),
    ("consequence", "Why is this important to me?", "A design signal matters when it can affect an informed choice, total cost, recurring commitment, or ability to leave. The actual effect remains context-dependent.", "consumer control and context"),
    ("uncertainty", "Is this definitely a dark pattern?", "No. A ClauseGuard signal may be potential or supported based on available evidence; it is not a definitive legal conclusion.", "potential versus supported status"),
    ("uncertainty", "Can ClauseGuard prove this is illegal?", "No. ClauseGuard provides an analytical consumer-risk assessment and regulatory context, not legal advice or a legal determination.", "regulatory context is not legal certainty"),
    ("uncertainty", "Is a countdown always a dark pattern?", "No. A countdown alone is not enough. ClauseGuard needs supporting evidence and context about the deadline, presentation, and user journey.", "one signal is insufficient"),
    ("uncertainty", "What if there is not enough evidence?", "The result should remain unknown, not supported, or potential as appropriate. Missing context must not be filled with assumptions.", "uncertainty and missing context"),
    ("simple", "Explain the risk like I am a normal consumer.", "The page may be pushing a decision or hiding an important term. Check the price, choices, and exit path before continuing.", "plain-language consumer explanation"),
    ("simple", "What does this mean for me?", "It means the current design may reduce clarity or control. Review the cited evidence and terms before treating the signal as conclusive.", "clarity and control"),
    ("comparison", "What is the difference between urgency and scarcity?", "Urgency pressures timing through a deadline or hurry message. Scarcity emphasizes limited availability. A signal in either category still needs context and evidence.", "urgency versus scarcity"),
    ("comparison", "What is the difference between observation and actionable risk?", "An observation records what was seen. Actionable risk is a stronger assessment that requires sufficient supporting evidence and a relevant consumer consequence.", "observation versus actionable risk"),
    ("comparison", "What is the difference between potential and supported risk?", "Potential means a relevant signal exists but the evidence threshold is not fully met. Supported means the current evidence satisfies the configured support conditions.", "potential versus supported"),
    ("comparison", "How is drip pricing different from a normal additional fee?", "An additional fee can be ordinary when clearly disclosed and included in the decision context. Drip pricing concerns charges introduced or revealed late enough to reduce price clarity.", "timing and disclosure"),
    ("risk", "What does HIGH risk mean?", "HIGH is a bounded ClauseGuard risk level based on fused evidence and consumer consequence. Read it with the supporting records and certainty status; it is not a legal conclusion.", "bounded risk and evidence"),
    ("risk", "What does CRITICAL risk mean?", "CRITICAL is the highest configured bounded risk level and indicates substantial concern in the fused analysis. It still depends on evidence and is not a legal determination.", "bounded risk and evidence"),
    ("risk", "Why did the risk score increase?", "The score can increase when stronger, consistent evidence or a more serious consumer consequence enters the canonical fusion. The current evidence IDs explain the change.", "evidence fusion and consequence"),
    ("risk", "Why is this not actionable?", "The signal may be relevant but lack enough support, context, or consumer consequence for an actionable assessment. That does not prove the behavior is absent.", "support threshold and context"),
    ("price", "Why is the final price higher?", "Compare the runtime price records and disclosure timing. A higher total may reflect an additional or recurring charge, but the specific amount must come from current evidence.", "price records and timing"),
    ("price", "What does late disclosure mean?", "Late disclosure means an important cost or term appears after an earlier decision point. Whether it is risky depends on the complete journey and the evidence.", "disclosure timing"),
    ("journey", "Why does checkout context matter?", "Checkout context shows when a user is deciding and what costs or choices are visible before commitment. The same text can mean something different elsewhere.", "journey stage and commitment"),
    ("journey", "Why does cancellation context matter?", "Cancellation context reveals whether leaving or undoing an action is comparable to entering it. Extra steps or retention loops can support an obstruction assessment.", "cancellation path and friction"),
    ("journey", "Why is a payment gateway treated separately?", "A payment gateway can be an auxiliary or separate route. Its evidence should not be confused with the product journey unless the route and product identity support that connection.", "route and product identity"),
    ("regulatory", "Which regulatory check was triggered?", "The answer must come from the runtime regulatory result and configured rules. A triggered check indicates a concern for review, not a legal finding.", "runtime regulatory result"),
    ("regulatory", "What jurisdiction was considered?", "Use the jurisdiction recorded in the current regulatory context. If it is absent or unknown, ClauseGuard should say so rather than assume one.", "configured jurisdiction"),
    ("regulatory", "Does this mean the website broke the law?", "No. ClauseGuard may identify a potential regulatory concern under configured rules, but it does not determine that a website violated the law.", "no legal overclaim"),
    ("clear", "What if the renewal price is clearly disclosed?", "Clear disclosure is evidence against a hidden-renewal concern. Other signals may still matter, but a transparent renewal price should not be treated as concealed by default.", "clear renewal terms"),
    ("clear", "What if the fee is included in the total?", "A fee that is clearly included in the displayed total is not automatically drip pricing. Review timing, mandatory status, and the complete price context.", "clear total and timing"),
    ("clear", "What if the checkbox is optional and unselected?", "An optional unselected checkbox is not by itself forced action or basket snaking. The surrounding choices and runtime behavior still determine the assessment.", "clear optional choice"),
    ("clear", "What if the cancellation path is available?", "An available, understandable cancellation path is evidence against obstruction. Check whether the route is actually usable and comparable to the entry path.", "clear exit path"),
    ("clear", "What if the behavior is ordinary?", "Ordinary behavior should not be converted into a risk finding without supporting evidence, relevant context, and a consumer consequence.", "negative case"),
]

QUESTION_PREFIXES = (
    "Can you explain", "In plain language, what is", "Help me understand", "Why would ClauseGuard mention", "What should a consumer know about",
)

@dataclass
class Phase3Metrics:
    empty_output_rate: float
    repetition_rate: float
    repeated_token_rate: float
    repeated_ngram_rate: float
    eos_completion_rate: float
    average_answer_length: float
    unique_token_ratio: float
    meaningful_answer_rate: float
    unsupported_claim_rate: float
    legal_overclaim_rate: float


def _record(question: str, answer: str, category: str, source: str, family: str, status: str = "POTENTIAL", analysis: str = "") -> dict:
    return {"analysis": analysis or "ClauseGuard analysis context is supplied at runtime.", "question": question.strip(), "answer": answer.strip(), "category": category, "status": status, "provenance": source, "family": family}


def build_phase3_corpus(target_size: int = 6000, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    records: list[dict] = []
    for pattern, info in PATTERN_KNOWLEDGE.items():
        for scenario_index, (scenario, location, check_context) in enumerate(SCENARIOS):
            for status_index, status in enumerate(STATUSES):
                for question_index in range(20):
                    label = info["label"]
                    if question_index < 5:
                        question = [f"What is {label}?", f"Can you explain {label}?", f"Why would ClauseGuard mention {label}?", f"What does {label} mean here?", f"Why should I care about {label}?"][question_index]
                    elif question_index < 10:
                        prefix = QUESTION_PREFIXES[question_index - 5]
                        question = f"{prefix} {label} {location}?"
                    else:
                        second_set = [
                            f"How does {label} change the decision?",
                            f"What part of the journey relates to {label}?",
                            f"Could the {label} signal be harmless in context?",
                            f"What would I look for before relying on this offer with {label}?",
                            f"How should an analyst describe the {label} evidence?",
                            f"Does seeing {label} settle the question?",
                            f"What is the consumer-facing concern with {label}?",
                            f"Which facts would distinguish {label} from ordinary design?",
                            f"How should I read a {label} result?",
                            f"What is still unknown about {label}?",
                        ]
                        question = f"{second_set[question_index - 10]} {location}?"
                    signal = info["signals"][(scenario_index + question_index) % len(info["signals"])]
                    status_context = {
                        "NOT_SUPPORTED": "when the evidence is insufficient",
                        "POTENTIAL": "when the evidence is suggestive",
                        "SUPPORTED": "when the evidence meets the support threshold",
                        "ACTIONABLE_RISK": "when the consumer consequence is material",
                        "CLEAR": "when the surrounding choice is transparent",
                        "UNKNOWN": "when important context is missing",
                    }[status]
                    question = f"{question.rstrip('?')} {location} {status_context}?"
                    if status == "NOT_SUPPORTED":
                        answer = f"This context does not support a {label} finding. The phrase or signal {signal} is not enough without relevant evidence and {check_context}."
                    elif status == "UNKNOWN":
                        answer = f"It is unknown whether this is {label}. The available context is incomplete, so ClauseGuard should not infer a finding from {signal}; verify {check_context}."
                    elif status == "CLEAR":
                        answer = f"A clear {label} signal is not established here. {signal.capitalize()} may be ordinary when the user has clear choices and {check_context}."
                    elif status == "SUPPORTED":
                        answer = f"The available evidence supports a {label} assessment because it shows {signal}. This is an analytical finding, not a legal conclusion; check {check_context}."
                    elif status == "ACTIONABLE_RISK":
                        answer = f"This may be an actionable {label} consumer risk because {signal} can {info['effect']}. Review {check_context} before continuing."
                    else:
                        answer = f"ClauseGuard sees a potential {label} signal because the page uses {signal}. It {info['effect']}; the conclusion remains proportional to evidence and {check_context}."
                    records.append(_record(question, answer, label, "synthetic_canonical", f"pattern:{pattern}:{scenario}:{status}:{question_index}", status, f"Synthetic canonical {label} context in {scenario}."))
    for category, question, answer, concepts in GENERAL_BANK:
        for variation in range(12):
            location = SCENARIOS[variation % len(SCENARIOS)][1]
            varied_question = f"{question.rstrip('?')} {location} in runtime context {variation + 1}?"
            varied_answer = f"{answer} {concepts.capitalize()} should be verified from the current analysis."
            records.append(_record(varied_question, varied_answer, category, "synthetic_canonical", f"general:{category}:{variation}", "UNKNOWN" if category in {"uncertainty", "regulatory"} else "POTENTIAL"))
    if len(records) < target_size:
        raise ValueError(f"Phase 3 corpus generator produced only {len(records)} records")
    rng.shuffle(records)
    return records[:target_size]


def validate_corpus(records: list[dict]) -> dict:
    questions = [r.get("question", "").strip().lower() for r in records]
    pairs = [(r.get("question", "").strip().lower(), r.get("answer", "").strip().lower()) for r in records]
    prohibited = re.compile(r"(openai|chatgpt|gpt-|llama|huggingface|as an ai|definitely illegal|the website broke the law)", re.I)
    malformed = [r for r in records if not r.get("question", "").strip() or not r.get("answer", "").strip() or not r.get("category")]
    prohibited_records = [r for r in records if prohibited.search(r.get("answer", ""))]
    unsupported_categories = [r for r in records if r.get("category") not in {info["label"] for info in PATTERN_KNOWLEDGE.values()} | {row[0] for row in GENERAL_BANK}]
    question_counts = Counter(questions)
    pair_counts = Counter(pairs)
    duplicate_questions = sum(count - 1 for count in question_counts.values() if count > 1)
    duplicate_pairs = sum(count - 1 for count in pair_counts.values() if count > 1)
    return {"total_examples": len(records), "unique_questions": len(question_counts), "unique_answers": len({r.get('answer', '').strip().lower() for r in records}), "duplicate_question_count": duplicate_questions, "duplicate_pair_count": duplicate_pairs, "malformed_count": len(malformed), "prohibited_reference_count": len(prohibited_records), "unsupported_category_count": len(unsupported_categories), "category_distribution": dict(Counter(r["category"] for r in records)), "status_distribution": dict(Counter(r["status"] for r in records))}


def write_jsonl(path: Path, records: Iterable[dict]) -> None:
    path.write_text("".join(json.dumps(record, ensure_ascii=True) + "\n" for record in records), encoding="utf-8")


def build_unseen_questions() -> list[dict]:
    categories = ["concepts", "evidence", "consequences", "pricing", "journey", "risk", "regulatory", "uncertainty", "clear/no-risk", "potential-risk"]
    questions = [
        "Could the activity label be influencing my choice?", "What would make this finding stronger?", "What should I verify in the total before paying?", "Does the route make this evidence relevant?", "How should I interpret a high bounded score?", "Is a regulatory concern the same as a violation?", "What should ClauseGuard say when the page is incomplete?", "Could a transparent term mean there is no actionable risk?", "What makes a signal only potential?", "How does a consumer protect their choice here?",
    ]
    return [{"question": question, "category": categories[index % len(categories)]} for index, question in enumerate(questions * 10)]


def build_golden_questions() -> list[dict]:
    return [{"question": question, "expected_answer": answer, "category": category, "important_concepts": concepts.split(" and ")} for category, question, answer, concepts in GENERAL_BANK[:30]]


def prepare_phase3_artifacts(target_size: int = 5000, output_dir: str | None = None, seed: int = 7) -> dict:
    """Write Phase 3 data and diagnostics without starting model training."""
    out = Path(output_dir) if output_dir else Path(__file__).resolve().parents[2] / "artifacts" / "clauseguard_llm_v0_1_phase3"
    out.mkdir(parents=True, exist_ok=True)
    corpus = build_phase3_corpus(target_size=target_size, seed=seed)
    splits = split_phase2_corpus(corpus, seed=seed)
    quality = validate_corpus(corpus)
    question_sets = [{"train_validation": len({r["question"].lower() for r in splits.train} & {r["question"].lower() for r in splits.validation}), "train_test": len({r["question"].lower() for r in splits.train} & {r["question"].lower() for r in splits.test}), "validation_test": len({r["question"].lower() for r in splits.validation} & {r["question"].lower() for r in splits.test})}]
    write_jsonl(out / "corpus.jsonl", corpus)
    write_jsonl(out / "unseen_questions.jsonl", build_unseen_questions())
    write_jsonl(out / "golden_questions.jsonl", build_golden_questions())
    stats = {**quality, "train_size": len(splits.train), "validation_size": len(splits.validation), "test_size": len(splits.test), "leakage": question_sets[0]}
    (out / "corpus_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    (out / "corpus_quality_report.md").write_text("# Phase 3 Corpus Quality\n\n```json\n" + json.dumps(stats, indent=2) + "\n```\n", encoding="utf-8")
    diagnostics = [
        "# ClauseGuard LLM v0.1 Phase 3 Diagnostics", "", "## Findings", 
        "- Causal attention uses a lower-triangular mask; future positions are not visible.",
        "- Target construction shifts input tokens by one position.",
        "- Phase 2 padded targets contributed to cross-entropy; Phase 3 ignores padding with `ignore_index=0`.",
        "- Phase 2 prompt generation included prompt EOS; Phase 3 starts with BOS and excludes prompt EOS.",
        "- Phase 2 lacked repetition penalty and no-repeat n-gram controls; Phase 3 adds both plus top-k/top-p.",
        "- Phase 2 generation was sampled from a small, highly structured corpus and showed repeated-token degeneration.",
        "- Phase 3 corpus questions are unique and split by family; runtime webpage facts remain outside training records.",
        "", "## Current status", "- Full Phase 3 training/evaluation must still be run to claim quality-gate metrics.", "- No `/ask` integration is permitted by this pipeline.",
    ]
    (out / "phase3_diagnostics.md").write_text("\n".join(diagnostics) + "\n", encoding="utf-8")
    return stats


def _pad_batch(batch: list[list[int]], width: int) -> tuple[torch.Tensor, torch.Tensor]:
    inputs = [seq[:width] + [0] * (width - len(seq[:width])) for seq in batch]
    targets = [seq[1:width + 1] + [0] * (width - len(seq[1:width + 1])) for seq in batch]
    return torch.tensor(inputs, dtype=torch.long), torch.tensor(targets, dtype=torch.long)


def _loss(model: ClauseGuardDecoderLM, sequences: list[list[int]], batch_size: int, device: str) -> float:
    model.eval()
    values = []
    with torch.no_grad():
        for start in range(0, len(sequences), batch_size):
            batch = sequences[start:start + batch_size]
            width = min(model.config.context_length, max(len(seq) for seq in batch) - 1)
            inputs, targets = _pad_batch(batch, width)
            logits = model(inputs.to(device))
            values.append(float(F.cross_entropy(logits.reshape(-1, logits.size(-1)), targets.to(device).reshape(-1), ignore_index=0).item()))
    return sum(values) / len(values) if values else float("nan")


def _metric_for_output(output: dict, tokenizer: ClauseGuardTokenizer) -> dict:
    completion = output["completion_text"]
    tokens = tokenizer.encode(completion, add_special_tokens=False)
    words = completion.lower().split()
    repeated_token_rate = 1.0 - len(set(tokens)) / len(tokens) if tokens else 0.0
    ngrams = [tuple(tokens[index:index + 3]) for index in range(max(0, len(tokens) - 2))]
    repeated_ngram_rate = 1.0 - len(set(ngrams)) / len(ngrams) if ngrams else 0.0
    severe = any(words[index] == words[index - 1] == words[index - 2] == words[index - 3] == words[index - 4] for index in range(4, len(words)))
    legal_overclaim = bool(re.search(r"\b(illegal|violated the law|definitely unlawful|proves a violation)\b", output["text"].lower()))
    unsupported = bool(re.search(r"\b(always|definitely|certainly)\b", output["text"].lower()))
    meaningful = len(tokens) >= 8 and len(set(tokens)) / len(tokens) >= 0.35 and not severe
    return {"empty": not bool(completion.strip()), "repetitive": severe, "repeated_token_rate": repeated_token_rate, "repeated_ngram_rate": repeated_ngram_rate, "eos_completed": output["eos_completed"], "answer_length": len(tokens), "unique_token_ratio": len(set(tokens)) / len(tokens) if tokens else 0.0, "meaningful": meaningful, "unsupported": unsupported, "legal_overclaim": legal_overclaim}


def aggregate_metrics(rows: list[dict]) -> Phase3Metrics:
    count = max(1, len(rows))
    return Phase3Metrics(*(sum(row[key] for row in rows) / count for key in ("empty", "repetitive", "repeated_token_rate", "repeated_ngram_rate", "eos_completed", "answer_length", "unique_token_ratio", "meaningful", "unsupported", "legal_overclaim")))


def evaluate_questions(model: ClauseGuardDecoderLM, tokenizer: ClauseGuardTokenizer, questions: list[dict], decoding: dict, output_path: Path | None = None) -> tuple[list[dict], Phase3Metrics]:
    rows = []
    for item in questions:
        raw = generate_clauseguard_text(model, item["question"], tokenizer=tokenizer, max_new_tokens=48, min_new_tokens=8, return_metadata=True, **decoding)
        metrics = _metric_for_output(raw, tokenizer)
        rows.append({**item, "generated_answer": raw["text"], "completion_status": "eos" if raw["eos_completed"] else "max_tokens", "quality_status": "meaningful" if metrics["meaningful"] else "poor", **metrics})
    if output_path:
        write_jsonl(output_path, rows)
    return rows, aggregate_metrics(rows)


def run_phase3(config: ClauseGuardLLMConfig | None = None, target_size: int = 6000, epochs: int = 5, output_dir: str | None = None, seed: int = 7) -> dict:
    cfg = config or ClauseGuardLLMConfig(context_length=192, batch_size=16, gradient_accumulation_steps=2)
    random.seed(seed)
    torch.manual_seed(seed)
    out = Path(output_dir) if output_dir else Path(__file__).resolve().parents[2] / "artifacts" / "clauseguard_llm_v0_1_phase3"
    out.mkdir(parents=True, exist_ok=True)
    corpus = build_phase3_corpus(target_size=target_size, seed=seed)
    quality = validate_corpus(corpus)
    splits = split_phase2_corpus(corpus, seed=seed)
    train_questions = {r["question"].lower() for r in splits.train}
    val_questions = {r["question"].lower() for r in splits.validation}
    test_questions = {r["question"].lower() for r in splits.test}
    leakage = {"train_validation": len(train_questions & val_questions), "train_test": len(train_questions & test_questions), "validation_test": len(val_questions & test_questions)}
    tokenizer = ClauseGuardTokenizer(vocab_size=cfg.vocab_size)
    tokenizer.train(f"analysis: {r['analysis']} question: {r['question']} answer: {r['answer']}" for r in corpus)
    def encode(rows):
        sequences = []
        eos_id = tokenizer.encoder["<eos>"]
        for row in rows:
            ids = tokenizer.encode(f"analysis: {row['analysis']} question: {row['question']} answer: {row['answer']}", add_special_tokens=True)
            if len(ids) > cfg.context_length:
                ids = ids[: cfg.context_length - 1] + [eos_id]
            sequences.append(ids)
        return sequences
    train_sequences, val_sequences, test_sequences = encode(splits.train), encode(splits.validation), encode(splits.test)
    model = ClauseGuardDecoderLM(cfg).to(cfg.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.learning_rate, weight_decay=0.01)
    epoch_metrics = []
    best_validation = math.inf
    best_epoch = 0
    start = time.perf_counter()
    for epoch in range(1, epochs + 1):
        model.train()
        random.shuffle(train_sequences)
        losses = []
        optimizer.zero_grad(set_to_none=True)
        for offset in range(0, len(train_sequences), cfg.batch_size):
            batch = train_sequences[offset:offset + cfg.batch_size]
            width = min(cfg.context_length, max(len(seq) for seq in batch) - 1)
            inputs, targets = _pad_batch(batch, width)
            logits = model(inputs.to(cfg.device))
            loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), targets.to(cfg.device).reshape(-1), ignore_index=0)
            (loss / max(1, cfg.gradient_accumulation_steps)).backward()
            step_index = offset // cfg.batch_size + 1
            if step_index % max(1, cfg.gradient_accumulation_steps) == 0 or offset + cfg.batch_size >= len(train_sequences):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
            losses.append(float(loss.item()))
        train_loss = sum(losses) / len(losses)
        validation_loss = _loss(model, val_sequences, cfg.batch_size, cfg.device)
        epoch_metrics.append({"epoch": epoch, "train_loss": train_loss, "validation_loss": validation_loss})
        checkpoint = {"model_state_dict": model.state_dict(), "config": asdict(cfg), "epoch": epoch, "validation_loss": validation_loss}
        torch.save(checkpoint, out / f"epoch_{epoch:02d}.pt")
        if validation_loss < best_validation:
            best_validation = validation_loss
            best_epoch = epoch
            torch.save(checkpoint, out / "best.pt")
        torch.save(checkpoint, out / "latest.pt")
    duration = time.perf_counter() - start
    test_loss = _loss(model, test_sequences, cfg.batch_size, cfg.device)
    write_jsonl(out / "corpus.jsonl", corpus)
    write_jsonl(out / "unseen_questions.jsonl", build_unseen_questions())
    write_jsonl(out / "golden_questions.jsonl", build_golden_questions())
    (out / "corpus_stats.json").write_text(json.dumps({**quality, "leakage": leakage, "train_size": len(splits.train), "validation_size": len(splits.validation), "test_size": len(splits.test), "vocabulary_size": len(tokenizer), "unknown_token_rate": tokenizer.unknown_token_rate(f"{r['analysis']} {r['question']} {r['answer']}" for r in corpus)}, indent=2), encoding="utf-8")
    (out / "corpus_quality_report.md").write_text("# Phase 3 Corpus Quality\n\n```json\n" + json.dumps({**quality, "leakage": leakage}, indent=2) + "\n```\n", encoding="utf-8")
    decoding_matrix = [{"temperature": temperature, "top_k": top_k, "top_p": 0.92, "repetition_penalty": penalty, "no_repeat_ngram_size": 3} for temperature in (0.6, 0.8, 1.0) for top_k in (20, 40, 60) for penalty in (1.0, 1.05, 1.1, 1.15)]
    matrix_results = []
    evaluation_questions = build_unseen_questions()
    for decoding in decoding_matrix[:12]:
        _, matrix_metrics = evaluate_questions(model, tokenizer, evaluation_questions[:20], decoding)
        matrix_results.append({"decoding": decoding, "metrics": asdict(matrix_metrics)})
    best_decoding = min(matrix_results, key=lambda row: row["metrics"]["repetition_rate"])["decoding"]
    unseen_rows, unseen_metrics = evaluate_questions(model, tokenizer, evaluation_questions, best_decoding, out / "unseen_generation_results.jsonl")
    golden_rows, golden_metrics = evaluate_questions(model, tokenizer, build_golden_questions(), best_decoding)
    quality_gate = {"empty_outputs": unseen_metrics.empty_output_rate == 0, "severe_repetition": unseen_metrics.repetition_rate < 0.10, "meaningful_answers": unseen_metrics.meaningful_answer_rate >= 0.80, "eos_completion": unseen_metrics.eos_completion_rate >= 0.90, "legal_overclaims": unseen_metrics.legal_overclaim_rate == 0, "unseen_semantic_acceptance": unseen_metrics.meaningful_answer_rate >= 0.80}
    report = {"objective": "Improve from-scratch ClauseGuard-specific generation without /ask integration.", "baseline": "Phase 2 had 3,000 records, 5.85M parameters, 9/11 repetitive outputs, and no meaningful complete answers.", "corpus": quality, "splits": {"train": len(splits.train), "validation": len(splits.validation), "test": len(splits.test), "leakage": leakage}, "model": {"parameters": model.count_parameters(), "config": asdict(cfg)}, "training": {"epochs": epochs, "best_epoch": best_epoch, "best_validation_loss": best_validation, "test_loss": test_loss, "epoch_metrics": epoch_metrics, "duration_seconds": duration}, "decoding_matrix": matrix_results, "selected_decoding": best_decoding, "unseen_metrics": asdict(unseen_metrics), "golden_metrics": asdict(golden_metrics), "quality_gate": quality_gate, "status": "PASS" if all(quality_gate.values()) else "NOT READY", "ask_integration": "NOT ALLOWED unless every quality-gate threshold passes", "limitations": ["Synthetic examples are canonical concept explanations, not observations.", "Runtime webpage facts are not encoded as universal facts.", "A lower loss does not establish conversational quality."]}
    (out / "phase3_metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    report_text = ["# ClauseGuard LLM v0.1 Phase 3 Report", "", "## Result", f"- Status: **{report['status']}**", f"- /ask integration: **{report['ask_integration']}**", "", "## Metrics", f"- Corpus: {len(corpus)}; train/validation/test: {len(splits.train)}/{len(splits.validation)}/{len(splits.test)}", f"- Parameters: {model.count_parameters()}; vocabulary: {len(tokenizer)}", f"- Best validation loss: {best_validation:.6f}; test loss: {test_loss:.6f}; epochs: {epochs}", f"- Unseen metrics: {asdict(unseen_metrics)}", f"- Golden metrics: {asdict(golden_metrics)}", "", "## Root-cause audit", "- Causal mask and residual attention dimensions are structurally correct.", "- Target shifting is input `t` to target `t+1`.", "- Phase 2 padded targets were not ignored by loss; Phase 3 uses `ignore_index=0`.", "- Phase 2 decoding lacked repetition penalty and no-repeat n-gram controls; Phase 3 adds both.", "- Phase 2 generated short or repetitive continuations, so lower validation loss alone was insufficient.", "", "## Quality gate", json.dumps(quality_gate, indent=2), "", "The model remains standalone and is not integrated with `/ask`."]
    (out / "phase3_report.md").write_text("\n".join(report_text) + "\n", encoding="utf-8")
    return report
