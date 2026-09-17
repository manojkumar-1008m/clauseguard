from __future__ import annotations

import math
from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F

from .config import SmokeTestConfig


class CausalSelfAttention(nn.Module):
    def __init__(self, embedding_dim: int, num_heads: int, dropout: float = 0.1):
        super().__init__()
        self.embedding_dim = embedding_dim
        self.num_heads = num_heads
        self.head_dim = embedding_dim // num_heads
        if self.head_dim * num_heads != embedding_dim:
            raise ValueError("embedding_dim must be divisible by num_heads")
        self.q_proj = nn.Linear(embedding_dim, embedding_dim)
        self.k_proj = nn.Linear(embedding_dim, embedding_dim)
        self.v_proj = nn.Linear(embedding_dim, embedding_dim)
        self.out_proj = nn.Linear(embedding_dim, embedding_dim)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor, mask: torch.Tensor | None = None):
        b, t, c = x.shape
        q = self.q_proj(x).view(b, t, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(b, t, self.num_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(b, t, self.num_heads, self.head_dim).transpose(1, 2)
        scores = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(self.head_dim)
        if mask is not None:
            scores = scores.masked_fill(mask == 0, -1e9)
        attn = torch.softmax(scores, dim=-1)
        attn = self.dropout(attn)
        context = torch.matmul(attn, v).transpose(1, 2).contiguous().view(b, t, c)
        return self.out_proj(context)


class FeedForward(nn.Module):
    def __init__(self, embedding_dim: int, feedforward_dim: int, dropout: float = 0.1):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(embedding_dim, feedforward_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(feedforward_dim, embedding_dim),
            nn.Dropout(dropout),
        )

    def forward(self, x: torch.Tensor):
        return self.net(x)


class TransformerBlock(nn.Module):
    def __init__(self, embedding_dim: int, num_heads: int, feedforward_dim: int, dropout: float = 0.1):
        super().__init__()
        self.ln1 = nn.LayerNorm(embedding_dim)
        self.attn = CausalSelfAttention(embedding_dim, num_heads, dropout)
        self.ln2 = nn.LayerNorm(embedding_dim)
        self.ffn = FeedForward(embedding_dim, feedforward_dim, dropout)

    def forward(self, x: torch.Tensor, causal_mask: torch.Tensor | None = None):
        x = x + self.attn(self.ln1(x), causal_mask)
        x = x + self.ffn(self.ln2(x))
        return x


class ClauseGuardDecoderLM(nn.Module):
    def __init__(self, config: SmokeTestConfig):
        super().__init__()
        self.config = config
        self.token_embedding = nn.Embedding(config.vocab_size, config.embedding_dim)
        self.position_embedding = nn.Embedding(config.context_length, config.embedding_dim)
        self.layers = nn.ModuleList([
            TransformerBlock(config.embedding_dim, config.num_heads, config.feedforward_dim, config.dropout)
            for _ in range(config.num_layers)
        ])
        self.ln_f = nn.LayerNorm(config.embedding_dim)
        self.head = nn.Linear(config.embedding_dim, config.vocab_size, bias=False)
        if getattr(config, "tie_weights", False):
            self.head.weight = self.token_embedding.weight
        self.dropout = nn.Dropout(config.dropout)
        self.apply(self._init_weights)

    def _init_weights(self, module):
        if isinstance(module, (nn.Linear, nn.Embedding)):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if isinstance(module, nn.Linear) and module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.LayerNorm):
            torch.nn.init.zeros_(module.bias)
            torch.nn.init.ones_(module.weight)

    def count_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def build_causal_mask(self, seq_len: int, device: torch.device):
        mask = torch.ones(seq_len, seq_len, device=device, dtype=torch.bool)
        tril = torch.tril(torch.ones(seq_len, seq_len, device=device, dtype=torch.bool))
        mask = mask * tril
        return mask.unsqueeze(0).unsqueeze(0)

    def forward(self, input_ids: torch.Tensor):
        if input_ids.dim() != 2:
            raise ValueError("input_ids must be 2D [batch, seq]")
        if input_ids.size(1) > self.config.context_length:
            input_ids = input_ids[:, -self.config.context_length:]
        batch_size, seq_len = input_ids.shape
        device = input_ids.device
        positions = torch.arange(seq_len, device=device).unsqueeze(0).expand(batch_size, -1)
        positions = positions.clamp(max=self.config.context_length - 1)
        x = self.token_embedding(input_ids) + self.position_embedding(positions)
        x = self.dropout(x)
        causal_mask = self.build_causal_mask(seq_len, device)
        for layer in self.layers:
            x = layer(x, causal_mask)
        x = self.ln_f(x)
        logits = self.head(x)
        return logits

    def generate(self, input_ids: torch.Tensor, max_new_tokens: int = 8, temperature: float = 1.0, top_k: int | None = None):
        self.eval()
        with torch.no_grad():
            generated = input_ids.clone()
            for _ in range(max_new_tokens):
                if generated.size(1) > self.config.context_length:
                    generated = generated[:, -self.config.context_length:]
                logits = self.forward(generated)[:, -1, :]
                logits = logits / max(temperature, 1e-8)
                if top_k is not None:
                    v, _ = torch.topk(logits, k=min(top_k, logits.size(-1)))
                    logits = torch.where(logits < v[:, -1, None], torch.full_like(logits, -1e9), logits)
                probs = torch.softmax(logits, dim=-1)
                next_token = torch.multinomial(probs, num_samples=1)
                generated = torch.cat([generated, next_token], dim=1)
            return generated
