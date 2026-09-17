# ClauseGuard LLM v0.1 Phase 4 Report

## Quality-gate decision
- Status: **NOT READY**
- /ask integration: **NOT ALLOWED**

## Objective
Answer arbitrary natural-language questions using supplied ClauseGuard analysis context.

## Baselines
- Phase 2: 5.85M model with repetitive generation and no meaningful complete answers in the baseline sample.
- Phase 3: 5,000-record infrastructure-complete corpus; full quality run was not completed.

## Corpus and model
- Corpus: 120 records; follow-up fraction: 0.233
- Parameters: 149248; unknown-token rate: 0.0000
- Canonical fields come from the existing AskClauseGuardContext and AskEvidence schemas.
- No pretrained weights or external APIs were used.

## Training
{
  "epochs": 1,
  "best_epoch": 1,
  "best_validation_loss": 40.66848373413086,
  "test_loss": 38.83343505859375,
  "epoch_metrics": [
    {
      "epoch": 1,
      "train_loss": 40.104783376057945,
      "validation_loss": 40.66848373413086
    }
  ],
  "duration_seconds": 108.41946800000005
}

## Evaluation
- Unseen: {"empty_output_rate": 0.0, "repetition_rate": 0.035, "repeated_token_rate": 0.6541872796615794, "repeated_ngram_rate": 0.002726845568224878, "eos_completion_rate": 0.035, "average_answer_length": 26.775, "unique_token_ratio": 0.34581272033842064, "meaningful_answer_rate": 0.965, "semantic_acceptance_rate": 0.8, "unsupported_claim_rate": 0.0, "hallucination_rate": 0.0, "legal_overclaim_rate": 0.015, "context_grounding_rate": 0.75}
- Golden: {"empty_output_rate": 0.0, "repetition_rate": 0.08, "repeated_token_rate": 0.6574617187315812, "repeated_ngram_rate": 0.00770131530873219, "eos_completion_rate": 0.02, "average_answer_length": 28.4, "unique_token_ratio": 0.3425382812684188, "meaningful_answer_rate": 0.92, "semantic_acceptance_rate": 0.88, "unsupported_claim_rate": 0.0, "hallucination_rate": 0.0, "legal_overclaim_rate": 0.06, "context_grounding_rate": 0.66}
- Context grounding: 1.000
- Multi-turn: {"empty_output_rate": 0.0, "repetition_rate": 0.05, "repeated_token_rate": 0.6553438362815843, "repeated_ngram_rate": 0.003125, "eos_completion_rate": 0.0, "average_answer_length": 30.15, "unique_token_ratio": 0.3446561637184157, "meaningful_answer_rate": 0.95, "semantic_acceptance_rate": 1.0, "unsupported_claim_rate": 0.05, "hallucination_rate": 0.05, "legal_overclaim_rate": 0.0, "context_grounding_rate": 0.65}

## Quality gate
{
  "empty_output_rate": true,
  "severe_repetition_rate": true,
  "meaningful_answer_rate": true,
  "semantic_acceptance_rate": true,
  "context_grounding_rate": true,
  "eos_completion_rate": false,
  "hallucination_rate": true,
  "legal_overclaim_rate": false,
  "external_api_usage": true,
  "pretrained_weights": true
}

The Phase 4 pipeline is standalone. Integration remains prohibited unless every gate passes.
