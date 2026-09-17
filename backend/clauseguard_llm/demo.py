from __future__ import annotations

from .config import ClauseGuardLLMConfig
from .full_training import build_clauseguard_domain_corpus, train_clauseguard_llm_phase2
from .generation import generate_clauseguard_text


def run_phase2_demo() -> dict:
    cfg = ClauseGuardLLMConfig(
        vocab_size=512,
        context_length=64,
        embedding_dim=64,
        num_layers=2,
        num_heads=4,
        feedforward_dim=128,
        batch_size=2,
        tie_weights=True,
    )
    model, stats = train_clauseguard_llm_phase2(config=cfg, steps=4, seed=7)
    prompts = [
        "ClauseGuard social proof risk",
        "Why did ClauseGuard flag this",
        "What evidence supports the finding",
        "Could this cost me more",
    ]
    outputs = {prompt: generate_clauseguard_text(model, prompt, max_new_tokens=12, temperature=1.0, top_k=20) for prompt in prompts}
    return {"stats": stats, "outputs": outputs, "corpus_size": len(build_clauseguard_domain_corpus())}


if __name__ == "__main__":
    print(run_phase2_demo())
