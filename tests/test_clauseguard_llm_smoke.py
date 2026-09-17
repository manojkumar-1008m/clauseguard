import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.clauseguard_llm import (
    ClauseGuardDecoderLM,
    ClauseGuardQADataset,
    ClauseGuardTokenizer,
    SmokeTestConfig,
    run_smoke_test,
)


def test_tokenizer_smoke():
    tokenizer = ClauseGuardTokenizer(vocab_size=128)
    corpus = [
        "ClauseGuard flagged social proof on the checkout journey.",
        "The user saw hidden fees and forced action.",
    ]
    tokenizer.train(corpus)
    encoded = tokenizer.encode("ClauseGuard flagged hidden fees.")
    assert len(encoded) > 0
    decoded = tokenizer.decode(encoded)
    assert isinstance(decoded, str)
    assert len(decoded) > 0


def test_dataset_and_model_smoke():
    config = SmokeTestConfig(
        vocab_size=128,
        context_length=32,
        embedding_dim=32,
        num_layers=2,
        num_heads=4,
        feedforward_dim=64,
        dropout=0.1,
        batch_size=2,
    )
    dataset = ClauseGuardQADataset(seed=7)
    sample = dataset[0]
    assert "input_ids" in sample
    assert "target_ids" in sample

    model = ClauseGuardDecoderLM(config)
    assert model.count_parameters() > 0
    assert model.training is True

    result = run_smoke_test(config=config, dataset=dataset, steps=3, seed=7)
    assert result["loss_finite"] is True
    assert result["gradients_nonzero"] is True
    assert result["parameters_changed"] is True
    assert result["checkpoint_saved"] is True
    assert result["checkpoint_loaded"] is True
    assert result["logits_valid"] is True
    assert result["generation_valid"] is True
    assert result["decoded_tokens_valid"] is True
