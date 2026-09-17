# ClauseGuard LLM v0.1

This package implements a small, real decoder-only causal Transformer for ClauseGuard analysis QA.

## Scope

This model is deliberately domain-specific. It is designed to answer ClauseGuard-style questions using runtime analysis context and learned ClauseGuard vocabulary. It is not a general-purpose ChatGPT-class model and does not rely on external pretrained weights.

## Smoke-test phase

The smoke-test configuration is intentionally tiny and CPU-safe:

- vocab_size: 2048
- context_length: 128
- embedding_dim: 128
- num_layers: 2
- num_heads: 4
- feedforward_dim: 512
- dropout: 0.1
- batch_size: 2

This phase proves the following work on CPU:

- tokenizer
- dataset
- model
- forward pass
- loss
- backward pass
- optimizer step
- checkpoint save/load
- generation

## Phase 2 configuration

The full v0.1 model is configured to be conservative for an Intel i5-9300H / 8GB CPU-only environment:

- vocab_size: 4096
- context_length: 256
- embedding_dim: 256
- num_layers: 6
- num_heads: 4
- feedforward_dim: 1024
- batch_size: 2–4
- gradient_accumulation_steps: 2–4

The exact parameter count is computed in code using the model config rather than assumed.

## Important constraints

- No pretrained GPT/Llama/Qwen/Mistral/BERT/MiniLM weights are used.
- Weight initialization is random.
- Runtime analysis context remains authoritative.
- The risk engine is not replaced.
- LLM output is used as a generated explanation path only.

## Current status

Phase 1 smoke test is implemented and verified. Phase 2 uses `phase2_training.py` to build a 3,000-record ClauseGuard-specific corpus from canonical concepts plus clearly marked observed/synthetic examples, create leakage-resistant train/validation/test splits, train from scratch, save checkpoints and tokenizer metadata, and run locked raw generation checks. It is not integrated with `/ask`.

Phase 3 uses `phase3_training.py` for a larger 6,000-record corpus, corpus-quality checks, unseen and golden evaluations, controlled decoding, multi-epoch checkpoints, and an explicit quality gate. It remains standalone and does not change `/ask`.
