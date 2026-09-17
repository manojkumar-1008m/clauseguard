# ClauseGuard LLM v0.1 Phase 4 Report

## Quality Gate Decision
- Status: **READY FOR /ask INTEGRATION**
- /ask Integration: **ALLOWED**

## Model & Capacity
- Parameters: **5,885,952** (Intended 5–7M: Yes)
- Context length: 384, Vocab size: 3317
- Unknown token rate: 0.0000

## Corpus Quality
- Total records: 12000
- Unique question rate: 1.000 (>= 0.90)
- Unique answer rate: 0.979 (>= 0.70)
- Repeated answer rate: 0.021 (<= 0.30)
- Template-only rate: 0.020 (<= 0.20)
- Forbidden legal claims: 0
- Malformed: 0

## Training Metrics
- Epochs: 2
- Best validation loss: inf
- Duration: 3319.2s

## Evaluation Metrics
- Unseen (200): meaningful=0.985, semantic=0.875, repetition=0.005, eos=1.000, hallucination=0.000, legal=0.000
- Golden (50): meaningful=0.960, semantic=0.860, repetition=0.040, eos=1.000
- Context grounding rate: 1.000

## Quality Gate Breakdown
```json
{
  "empty_output_rate": true,
  "severe_repetition_rate": true,
  "meaningful_answer_rate": true,
  "semantic_acceptance_rate": true,
  "context_grounding_rate": true,
  "eos_completion_rate": true,
  "hallucination_rate": true,
  "legal_overclaim_rate": true,
  "external_api_usage": true,
  "pretrained_weights": true
}
```

The Phase 4 pipeline is standalone. Integration remains prohibited unless every gate passes: PASSED
