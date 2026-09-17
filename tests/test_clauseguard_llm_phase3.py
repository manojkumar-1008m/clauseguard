import os
import sys

import torch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.clauseguard_llm import ClauseGuardDecoderLM, ClauseGuardTokenizer, SmokeTestConfig
from backend.clauseguard_llm.generation import generate_clauseguard_text
from backend.clauseguard_llm.phase3_training import build_phase3_corpus, validate_corpus


def test_phase3_corpus_is_unique_and_clauseguard_scoped():
    corpus = build_phase3_corpus(target_size=600)
    stats = validate_corpus(corpus)
    assert stats["malformed_count"] == 0
    assert stats["prohibited_reference_count"] == 0
    assert stats["unsupported_category_count"] == 0
    assert stats["duplicate_question_count"] == 0
    assert len({row["question"] for row in corpus}) == len(corpus)


def test_causal_mask_blocks_future_positions():
    config = SmokeTestConfig(vocab_size=32, context_length=8, embedding_dim=16, num_layers=1, num_heads=4, feedforward_dim=32)
    model = ClauseGuardDecoderLM(config)
    mask = model.build_causal_mask(4, torch.device("cpu"))[0, 0]
    assert bool(mask[0, 0]) is True
    assert bool(mask[0, 1]) is False
    assert bool(mask[3, 0]) is True
    assert bool(mask[3, 3]) is True


def test_controlled_generation_returns_metadata_and_respects_tokenizer():
    config = SmokeTestConfig(vocab_size=64, context_length=16, embedding_dim=16, num_layers=1, num_heads=4, feedforward_dim=32)
    model = ClauseGuardDecoderLM(config)
    tokenizer = ClauseGuardTokenizer(vocab_size=64)
    tokenizer.train(["ClauseGuard evidence supports a potential risk answer."])
    result = generate_clauseguard_text(model, "What is the risk?", tokenizer=tokenizer, max_new_tokens=5, min_new_tokens=2, top_k=8, top_p=0.9, repetition_penalty=1.1, no_repeat_ngram_size=2, return_metadata=True)
    assert 2 <= result["new_token_count"] <= 5
    assert isinstance(result["text"], str)
    assert len(result["token_ids"]) > 0
