from __future__ import annotations

import csv
import json
import random
from pathlib import Path

import torch
import torch.nn.functional as F

from .config import ClauseGuardLLMConfig
from .model import ClauseGuardDecoderLM


def build_clauseguard_domain_corpus(limit: int = 200, data_path: str | None = None) -> list[dict]:
    """Construct a ClauseGuard-focused corpus from the local data files.

    The model is intentionally limited to ClauseGuard domains such as social proof,
    urgency, scarcity, obstruction, consumer consequences, pricing, and evidence
    interpretation. No general-purpose trivia is included by design.
    """
    project_root = Path(__file__).resolve().parents[2]
    csv_path = Path(data_path) if data_path else project_root / "data" / "train_v3.csv"

    examples: list[dict] = []
    if csv_path.exists():
        with open(csv_path, "r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                pattern = (row.get("pattern_category") or row.get("pattern") or "").strip()
                text = (row.get("text") or "").strip()
                consequence = (row.get("consumer_consequence") or "").strip()
                if not pattern or not text or pattern.lower() == "none":
                    continue
                question_bank = [
                    "Why did ClauseGuard flag this?",
                    "What evidence supports the finding?",
                    "What does this pattern mean?",
                    "Could this cost me more?",
                    "What should I check before purchasing?",
                    "Is this definitely a dark pattern?",
                    "What could happen if I continue?",
                ]
                question = question_bank[len(examples) % len(question_bank)]
                answer = (
                    f"ClauseGuard identified a potential {pattern.lower()} signal. "
                    f"The page text suggests a consumer-risk pattern and the relevant evidence is: {text[:180]}. "
                    f"The likely consequence is: {consequence or 'higher friction and reduced consumer control.'}"
                )
                examples.append({
                    "analysis": f"ClauseGuard analysis: {pattern} signal detected in customer journey text. Evidence: {text[:200]}",
                    "question": question,
                    "answer": answer,
                })
                if len(examples) >= limit:
                    break

    if not examples:
        examples = [
            {
                "analysis": "ClauseGuard analysis: social proof pressure detected in the checkout journey.",
                "question": "Why did ClauseGuard flag this?",
                "answer": "ClauseGuard flagged this because the page uses social proof pressure to steer a consumer decision before the user has enough context.",
            },
            {
                "analysis": "ClauseGuard analysis: hidden fees and forced action were detected.",
                "question": "Could this cost me more?",
                "answer": "The evidence suggests a pricing risk because the final cost may not be clearly shown before the user is pushed to continue.",
            },
        ]

    return examples


def train_clauseguard_llm_phase2(config: ClauseGuardLLMConfig | None = None, corpus: list[dict] | None = None, steps: int = 10, seed: int = 7):
    cfg = config or ClauseGuardLLMConfig()
    random.seed(seed)
    torch.manual_seed(seed)
    dataset = corpus or build_clauseguard_domain_corpus()

    model = ClauseGuardDecoderLM(cfg)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.learning_rate)

    train_text = []
    for row in dataset:
        train_text.append(f"analysis: {row['analysis']} question: {row['question']} answer: {row['answer']}")

    tokenizer = None
    try:
        from .tokenizer import ClauseGuardTokenizer
        tokenizer = ClauseGuardTokenizer(vocab_size=cfg.vocab_size)
        tokenizer.train(train_text)
    except Exception:
        tokenizer = None

    sequences = []
    if tokenizer is not None:
        for text in train_text:
            seq = tokenizer.encode(text, add_special_tokens=False)[: cfg.context_length]
            if len(seq) >= 2:
                sequences.append(seq)
    else:
        for text in train_text:
            seq = [ord(ch) % cfg.vocab_size for ch in text][: cfg.context_length]
            if len(seq) >= 2:
                sequences.append(seq)

    if not sequences:
        raise ValueError("No valid training sequences were produced")

    losses = []
    for _ in range(steps):
        batch = random.sample(sequences, min(cfg.batch_size, len(sequences)))
        max_len = max(len(seq) for seq in batch)
        x_batch = []
        y_batch = []
        for seq in batch:
            x_seq = seq[:-1] + [0] * max(0, max_len - len(seq) + 1)
            y_seq = seq[1:] + [0] * max(0, max_len - len(seq) + 1)
            x_batch.append(x_seq[: cfg.context_length])
            y_batch.append(y_seq[: cfg.context_length])
        x_tensor = torch.tensor(x_batch, dtype=torch.long)
        y_tensor = torch.tensor(y_batch, dtype=torch.long)
        optimizer.zero_grad(set_to_none=True)
        logits = model(x_tensor)
        loss = F.cross_entropy(logits.view(-1, logits.size(-1)), y_tensor.view(-1), ignore_index=0)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.item()))

    stats = {
        "config": {
            "vocab_size": cfg.vocab_size,
            "context_length": cfg.context_length,
            "embedding_dim": cfg.embedding_dim,
            "num_layers": cfg.num_layers,
            "num_heads": cfg.num_heads,
            "feedforward_dim": cfg.feedforward_dim,
            "device": cfg.device,
            "tie_weights": cfg.tie_weights,
        },
        "parameter_count": model.count_parameters(),
        "losses": losses,
        "final_loss": losses[-1] if losses else float("nan"),
        "tokenizer": tokenizer is not None,
        "dataset_size": len(dataset),
        "model_name": cfg.domain_name,
    }
    return model, stats
