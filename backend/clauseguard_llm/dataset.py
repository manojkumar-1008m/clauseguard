from __future__ import annotations

import os
from typing import Dict, List


class ClauseGuardQADataset:
    """A tiny local QA dataset for smoke training. This is intentionally small and clauseguard-specific."""

    def __init__(self, seed: int = 0, corpus: List[str] | None = None):
        self.seed = seed
        self.corpus = corpus or [
            "ClauseGuard analysis: social proof was detected on the checkout journey.",
            "User question: why did ClauseGuard flag this page?",
            "Answer: ClauseGuard flagged social proof because the page used customer activity to pressure a decision.",
            "ClauseGuard analysis: hidden fees and forced action were detected.",
            "User question: could this cost me more than expected?",
            "Answer: The setup suggests a financial risk because additional fees or charges may be introduced later.",
            "ClauseGuard analysis: false urgency and scarcity were detected.",
            "User question: what should I check before purchasing?",
            "Answer: Review price, cancellation terms, and whether urgency is being used to push a fast decision.",
            "ClauseGuard analysis: cancellation friction and obstruction were found.",
            "User question: what evidence supports the flag?",
            "Answer: The evidence shows friction during cancellation and a reduction in user control over the purchase decision.",
            "ClauseGuard analysis: a dark pattern may be present in the subscription flow.",
            "User question: is this definitely a dark pattern?",
            "Answer: This is a potential signal, not a definitive legal conclusion, but the evidence suggests a risky design pattern.",
        ]

    def __len__(self) -> int:
        return len(self.corpus)

    def __getitem__(self, idx: int) -> Dict[str, List[int]]:
        text = self.corpus[idx % len(self.corpus)]
        tokens = [ord(ch) % 128 for ch in text]
        if len(tokens) < 4:
            tokens = tokens + [0] * (4 - len(tokens))
        return {"input_ids": tokens[:-1], "target_ids": tokens[1:]}

    @staticmethod
    def collate(batch):
        max_len = max(len(item["input_ids"]) for item in batch)
        input_ids = []
        target_ids = []
        for item in batch:
            inp = item["input_ids"] + [0] * (max_len - len(item["input_ids"]))
            tgt = item["target_ids"] + [0] * (max_len - len(item["target_ids"]))
            input_ids.append(inp)
            target_ids.append(tgt)
        return {"input_ids": input_ids, "target_ids": target_ids}
