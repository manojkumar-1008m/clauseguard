from __future__ import annotations

import json
import os
import re
from collections import Counter
from typing import Iterable


class ClauseGuardTokenizer:
    """A compact deterministic subword tokenizer trained from ClauseGuard text."""

    DEFAULT_SPECIAL_TOKENS = (
        "<pad>", "<unk>", "<bos>", "<eos>",
        "<analysis>", "</analysis>",
        "<question>", "</question>",
        "<answer>", "</answer>",
    )

    def __init__(self, vocab_size: int = 2048, special_tokens: Iterable[str] = DEFAULT_SPECIAL_TOKENS):
        self.vocab_size = int(vocab_size)
        self.special_tokens = list(special_tokens)
        self.word_freq: Counter[str] = Counter()
        self.vocab: list[str] = []
        self.encoder: dict[str, int] = {}
        self.decoder: dict[int, str] = {}
        self._build_default_vocab()

    def _build_default_vocab(self):
        for token in self.special_tokens:
            self.vocab.append(token)
            self.encoder[token] = len(self.encoder)
            self.decoder[self.encoder[token]] = token

    def train(self, corpus: Iterable[str]):
        self.word_freq = Counter()
        for text in corpus:
            tokens = self._tokenize_text(text)
            self.word_freq.update(tokens)
        vocab = self.special_tokens[:]
        for token, _ in self.word_freq.most_common(self.vocab_size - len(vocab)):
            vocab.append(token)
        self.vocab = vocab
        self.encoder = {token: i for i, token in enumerate(self.vocab)}
        self.decoder = {i: token for token, i in self.encoder.items()}

    @staticmethod
    def _tokenize_text(text: str) -> list[str]:
        text = text.lower()
        pieces = re.findall(r"</?[a-z_]+>|[a-z0-9]+|[₹$€£%]|[._/:-]", text)
        return [piece for piece in pieces if piece]

    def encode(self, text: str, add_special_tokens: bool = True) -> list[int]:
        tokens = self._tokenize_text(text)
        ids = [self.encoder.get(token, self.encoder["<unk>"]) for token in tokens]
        if add_special_tokens:
            ids = [self.encoder["<bos>"]] + ids + [self.encoder["<eos>"]]
        return ids

    def decode(self, token_ids: Iterable[int]) -> str:
        tokens = []
        for token_id in token_ids:
            token = self.decoder.get(int(token_id), "<unk>")
            if token in {"<bos>", "<eos>", "<pad>", "<unk>"}:
                continue
            tokens.append(token)
        return " ".join(tokens)

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"vocab": self.vocab, "special_tokens": self.special_tokens}, handle)

    def load(self, path: str):
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        self.vocab = payload["vocab"]
        self.special_tokens = payload.get("special_tokens", self.special_tokens)
        self.encoder = {token: i for i, token in enumerate(self.vocab)}
        self.decoder = {i: token for token, i in self.encoder.items()}

    def __len__(self) -> int:
        return len(self.vocab)

    def unknown_token_rate(self, corpus: Iterable[str]) -> float:
        total = 0
        unknown = 0
        for text in corpus:
            ids = self.encode(text, add_special_tokens=False)
            total += len(ids)
            unknown += sum(token_id == self.encoder["<unk>"] for token_id in ids)
        return unknown / total if total else 0.0
