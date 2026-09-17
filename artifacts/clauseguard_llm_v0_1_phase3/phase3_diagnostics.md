# ClauseGuard LLM v0.1 Phase 3 Diagnostics

## Findings
- Causal attention uses a lower-triangular mask; future positions are not visible.
- Target construction shifts input tokens by one position.
- Phase 2 padded targets contributed to cross-entropy; Phase 3 ignores padding with `ignore_index=0`.
- Phase 2 prompt generation included prompt EOS; Phase 3 starts with BOS and excludes prompt EOS.
- Phase 2 lacked repetition penalty and no-repeat n-gram controls; Phase 3 adds both plus top-k/top-p.
- Phase 2 generation was sampled from a small, highly structured corpus and showed repeated-token degeneration.
- Phase 3 corpus questions are unique and split by family; runtime webpage facts remain outside training records.

## Current status
- Full Phase 3 training/evaluation must still be run to claim quality-gate metrics.
- No `/ask` integration is permitted by this pipeline.
