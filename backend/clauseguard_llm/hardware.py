from __future__ import annotations

import math


def estimate_parameter_count(vocab_size: int, context_length: int, embedding_dim: int, num_layers: int, num_heads: int, feedforward_dim: int, tie_weights: bool = True) -> dict:
    head_dim = embedding_dim // num_heads
    if head_dim * num_heads != embedding_dim:
        raise ValueError("embedding_dim must be divisible by num_heads")

    token_embedding = vocab_size * embedding_dim
    position_embedding = context_length * embedding_dim
    attn_weights = 4 * embedding_dim * embedding_dim
    attn_biases = 4 * embedding_dim
    mlp = 2 * embedding_dim * feedforward_dim + feedforward_dim + embedding_dim
    layer_norm = 4 * embedding_dim
    per_layer = attn_weights + attn_biases + mlp + layer_norm
    transformer = num_layers * per_layer
    final_ln = 2 * embedding_dim
    lm_head = vocab_size * embedding_dim if not tie_weights else 0
    total = token_embedding + position_embedding + transformer + final_ln + lm_head
    return {
        "token_embedding": token_embedding,
        "position_embedding": position_embedding,
        "per_layer": per_layer,
        "transformer_total": transformer,
        "final_layer_norm": final_ln,
        "lm_head": lm_head,
        "total_parameters": int(total),
    }


def estimate_memory(model_params: int, optimizer_bits: int = 32, activation_factor: float = 0.15) -> dict:
    param_memory_bytes = model_params * (optimizer_bits / 8)
    optimizer_memory_bytes = model_params * (optimizer_bits / 8) * 2.0
    activation_memory_bytes = model_params * activation_factor * 8.0
    return {
        "parameter_memory_mb": param_memory_bytes / (1024 * 1024),
        "optimizer_memory_mb": optimizer_memory_bytes / (1024 * 1024),
        "activation_memory_mb": activation_memory_bytes / (1024 * 1024),
    }


def recommend_config(vocab_size: int = 8192, context_length: int = 256, embedding_dim: int = 256, num_layers: int = 4, num_heads: int = 4, feedforward_dim: int = 1024, target_ram_gb: float = 8.0) -> dict:
    estimates = estimate_parameter_count(vocab_size, context_length, embedding_dim, num_layers, num_heads, feedforward_dim)
    mem = estimate_memory(estimates["total_parameters"])
    recommendation = {
        "requested": {
            "vocab_size": vocab_size,
            "context_length": context_length,
            "embedding_dim": embedding_dim,
            "num_layers": num_layers,
            "num_heads": num_heads,
            "feedforward_dim": feedforward_dim,
        },
        "parameter_estimate": estimates,
        "memory_estimate": mem,
        "safe_for_8gb_cpu": mem["parameter_memory_mb"] + mem["optimizer_memory_mb"] + mem["activation_memory_mb"] < (target_ram_gb * 1024),
    }
    if not recommendation["safe_for_8gb_cpu"]:
        scale = max(0.5, (target_ram_gb * 1024) / (mem["parameter_memory_mb"] + mem["optimizer_memory_mb"] + mem["activation_memory_mb"]))
        recommendation["recommended_downgrade"] = {
            "embedding_dim": max(128, int(embedding_dim * scale)),
            "num_layers": max(2, int(num_layers * scale)),
            "feedforward_dim": max(512, int(feedforward_dim * scale)),
        }
    else:
        recommendation["recommended_downgrade"] = None
    return recommendation
