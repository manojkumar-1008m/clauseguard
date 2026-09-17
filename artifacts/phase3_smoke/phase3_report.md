# ClauseGuard LLM v0.1 Phase 3 Report

## Result
- Status: **NOT READY**
- /ask integration: **NOT ALLOWED unless every quality-gate threshold passes**

## Metrics
- Corpus: 500; train/validation/test: 399/50/51
- Parameters: 105984; vocabulary: 477
- Best validation loss: 7.100588; test loss: 7.081654; epochs: 5
- Unseen metrics: {'empty_output_rate': 0.0, 'repetition_rate': 0.02, 'repeated_token_rate': 0.5943520626260593, 'repeated_ngram_rate': 0.0029774053350045226, 'eos_completion_rate': 0.0, 'average_answer_length': 44.11, 'unique_token_ratio': 0.40564793737394067, 'meaningful_answer_rate': 0.88, 'unsupported_claim_rate': 0.0, 'legal_overclaim_rate': 0.0}
- Golden metrics: {'empty_output_rate': 0.0, 'repetition_rate': 0.03333333333333333, 'repeated_token_rate': 0.5992082682496199, 'repeated_ngram_rate': 0.004767441860465119, 'eos_completion_rate': 0.0, 'average_answer_length': 44.0, 'unique_token_ratio': 0.40079173175038013, 'meaningful_answer_rate': 0.8333333333333334, 'unsupported_claim_rate': 0.03333333333333333, 'legal_overclaim_rate': 0.0}

## Root-cause audit
- Causal mask and residual attention dimensions are structurally correct.
- Target shifting is input `t` to target `t+1`.
- Phase 2 padded targets were not ignored by loss; Phase 3 uses `ignore_index=0`.
- Phase 2 decoding lacked repetition penalty and no-repeat n-gram controls; Phase 3 adds both.
- Phase 2 generated short or repetitive continuations, so lower validation loss alone was insufficient.

## Quality gate
{
  "empty_outputs": true,
  "severe_repetition": true,
  "meaningful_answers": true,
  "eos_completion": false,
  "legal_overclaims": true,
  "unseen_semantic_acceptance": true
}

The model remains standalone and is not integrated with `/ask`.
