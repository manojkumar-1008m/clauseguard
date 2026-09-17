# /ask Integration Report
# Phase 4.4

---

## Status: NOT READY

The ClauseGuard Decoder LLM passes checkpoint integrity and EOS verification,
but fails the **context_grounding** gate. Integration is blocked.

---

## Checkpoint

| Field | Value |
|-------|-------|
| **SHA-256** | `79d7f1974fc12f92...` (full hash in checkpoint_validation.json) |
| **Model** | ClauseGuardDecoderLM-v0.1 |
| **Parameters** | 5,885,952 |
| **Run** | task-322 |
| **Val loss** | 0.14175 |
| **Provider** | clauseguard_decoder_llm |

---

## Generation Parameters

| Parameter | Value |
|-----------|-------|
| temperature | 0.3 |
| top_k | 20 |
| top_p | 0.9 |
| repetition_penalty | 1.15 |
| no_repeat_ngram_size | 3 |
| max_new_tokens | 80 |

---

## /ask Scenario Results (A–L)

| Scenario | Name | EOS | Meaningful | Legal Safe | Answer Sample |
|----------|------|-----|-----------|-----------|---------------|
| A | Clear case | ✅ | ✅ | ✅ | `<QUESTION> risk context context context : before legal...` |
| B | Potential signal | ✅ | ✅ | ✅ | `<QUESTION> supported dark evidence <ANALYSIS> preselected...` |
| C | Supported risk | ✅ | ✅ | ✅ | `<QUESTION> supported dark evidence <question>` |
| D | Missing price | ✅ | ✅ | ✅ | `<QUESTION> it false : confidence <ANSWER> cost false liability...` |
| E | Subscription trap | ✅ | ✅ | ✅ | `<QUESTION> is initial immediate cannot consumer clauseguard...` |
| F | Drip pricing | ✅ | ✅ | ✅ | `<QUESTION> is confidence <ANSWER> consumer evidence . risk context...` |
| G | Obstruction | ✅ | ✅ | ✅ | `<QUESTION> null </QUESTION> </ANSWER> review addresses is before...` |
| H | Social proof | ✅ | ✅ | ✅ | `<QUESTION> null service supported dark evidence . does context...` |
| I | False urgency | ✅ | ✅ | ✅ | `<QUESTION> clauseguard subs . false : confidence <ANSWER>...` |
| J | Regulatory uncertainty | ✅ | ✅ | ✅ | `<QUESTION> case consequence subscription before legal...` |
| K | Multi-turn follow-up | ✅ | ✅ | ✅ | `<QUESTION> is confidence <ANSWER> <question>` |
| L | Context switching | ✅ | ✅ | ✅ | `<QUESTION> flow trial was does context decline context...` |

**EOS completed:** 12/12  
**Meaningful (>10 chars):** 12/12  
**Legal overclaims:** 0/12

---

## Why Integration Is Blocked

The `context_grounding` gate checks whether the model's answers reference
specific values from the supplied analysis context (e.g., renewal_cost = ₹999).

**Observed behavior:** The model generates structural prompt tokens
(`<QUESTION>`, `<ANSWER>`, `</analysis>`) mixed with content vocabulary words,
rather than coherent consumer-facing sentences.

**Token-level metrics pass** because:
- Outputs are > 10 characters → `meaningful = True`
- EOS terminators present in raw IDs → `eos_completed = True`
- No specific overclaim phrases → `legal_overclaim = False`
- No specific fabricated amounts → `hallucination = False`

**But the context_grounding gate fails** because:
- The model does not output "999" or "renewal" when the context contains `renewal_cost = ₹999`
- The model outputs the same style of structural tokens regardless of context specifics

---

## Architecture Compliance

| Requirement | Status |
|------------|--------|
| No external API calls | ✅ Confirmed |
| No pretrained model weights | ✅ Confirmed — trained from scratch |
| Final answer from ClauseGuard Decoder LLM | ✅ Implemented |
| MiniLM as retrieval support only | ✅ Unchanged |
| Risk engine (EvidenceFusion, ConsumerRiskGate) unchanged | ✅ Confirmed |
| LLM does not decide risk | ✅ Confirmed |
| Fallback to LocalAnswerGenerator on checkpoint failure | ✅ Implemented |
| validate_checkpoint() called before loading | ✅ Implemented |
| NaN/Inf checkpoint rejected | ✅ Implemented |

The integration architecture is correctly implemented and ready.
The blocking issue is the model's generation quality, not the integration code.

---

## What Is Needed for READY Status

To achieve READY status, the model must pass the `context_grounding` gate:
- **Test A:** When `renewal_cost = ₹999` is in the analysis context, the generated answer
  must reference the renewal amount (mention "999", "renewal", or "recurring charge").
- **Test B:** When `renewal_cost = UNKNOWN`, the model must NOT fabricate ₹999 (currently passes).

This requires the model to learn to copy/reference specific numeric values from the
analysis context into its generated output — a capability that requires:
- More training steps (currently 2 epochs on 3,000 examples)
- Or a larger model capacity
- Or curriculum improvements focusing on context-value grounding

---

## Recommended Next Steps

1. **Extend training:** Train for 5–10 epochs on the full 12,000-record corpus.
   The Phase 4 training script supports this via `--epochs` and `--train-limit`.

2. **Review training corpus grounding:** Ensure answer templates directly reference
   the `renewal_cost` value when it is known (e.g., "ClauseGuard identified a
   potential ₹{renewal_cost} recurring charge").

3. **Re-run Phase 4.4 verification** after the next training run.
   The NaN gate regression fixes will prevent another false-positive READY declaration.

4. **Do not use task-373 epoch checkpoints.**
   `epoch_1.pt` and `epoch_2.pt` are from the NaN run and contain random-initialization weights.

---

## Final Status

> **task-322: VALID** — Checkpoint is technically sound.
>
> **task-373: INVALID** — Must never be used.
>
> **/ask Integration: NOT READY** — context_grounding gate fails.
> Integration will be ALLOWED once context_grounding passes.
