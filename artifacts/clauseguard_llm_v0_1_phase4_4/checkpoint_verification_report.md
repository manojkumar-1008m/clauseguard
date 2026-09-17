# ClauseGuard LLM — Checkpoint Verification Report
# Phase 4.4

---

## Checkpoint Identity

| Field | Value |
|-------|-------|
| **Path** | `artifacts/clauseguard_llm_v0_1_phase4/checkpoints/best.pt` |
| **File size** | 23,572,217 bytes |
| **SHA-256** | `79d7f1974fc12f92...` (see checkpoint_validation.json for full hash) |
| **Epoch** | 2 |
| **Val loss (stored in checkpoint)** | 0.14175094664096832 |
| **Val loss finite** | True |
| **Run** | task-322 |

---

## Architecture

| Field | Value |
|-------|-------|
| **Parameters (model.parameters())** | 5,885,952 |
| **Parameters (all tensors)** | 6,934,528 (includes non-tied embedding) |
| **In 5–7M range** | True |
| **Config matches** | True |
| **Vocab size** | 3,317 |
| **Context length** | 384 |

---

## Tensor Integrity (Op 2)

| Metric | Value |
|--------|-------|
| Total float32 tensors | Checked |
| NaN parameter count | **0** |
| Inf parameter count | **0** |
| All tensors finite | **True** |

> The checkpoint passes all tensor integrity checks. This is the task-322 checkpoint.

---

## Checkpoint History Note

task-373 ran after task-322 and **overwrote `epoch_1.pt` and `epoch_2.pt`** with NaN val_loss checkpoints.
However, `best.pt` survived intact because the NaN gate bug (`NaN < inf = False`) prevented it from being overwritten.

| File | Epoch | Val Loss | Source |
|------|-------|----------|--------|
| `best.pt` | 2 | **0.1418** | ✅ task-322 — VALID |
| `epoch_1.pt` | 1 | **NaN** | ❌ task-373 overwrite — INVALID |
| `epoch_2.pt` | 2 | **NaN** | ❌ task-373 overwrite — INVALID |

---

## Tokenizer

| Field | Value |
|-------|-------|
| Path | `artifacts/clauseguard_llm_v0_1_phase4/tokenizer/tokenizer.json` |
| Loaded OK | True |
| Vocab size | 3,317 |

---

## Generation Quality (Op 3 — 20 questions)

| Metric | Value | Gate |
|--------|-------|------|
| Meaningful answers (>10 chars) | 20/20 | ✅ PASS (≥ 80%) |
| EOS completed | 20/20 | ✅ PASS (≥ 90%) |
| Severely repetitive | 0/20 | ✅ PASS (< 10%) |

**Note on output quality:** The model generates structural prompt tokens (`<QUESTION>`, `<ANSWER>`,
`</analysis>`) mixed with content vocabulary. Outputs pass the token-level metrics (non-empty, EOS-terminated,
not severely repetitive) but do not form coherent consumer-facing natural language.
Example generated answer:
```
<QUESTION> is initial immediate cannot consumer clauseguard urges <QUESTION> it synthetic
</analysis> . false : confidence <ANSWER> disclosure <QUESTION> confirming <ANSWER> <question>
```

---

## EOS Verification from Raw Token IDs (Op 4)

| Metric | Value | Gate |
|--------|-------|------|
| EOS completion rate (raw IDs) | **1.000** | ✅ PASS (≥ 0.90) |
| At max_new_tokens boundary | No — EOS terminators present in raw IDs |

EOS is confirmed from raw token IDs, not inferred from max_new_tokens. The `<eos>` or `</answer>` token
is present in the generated token sequences.

---

## Context Grounding (Op 5)

| Test | Expected | Result |
|------|----------|--------|
| A: ₹999 context → mention ₹999 | Output mentions "999"/"renewal"/"recurring" | **FAIL** |
| B: UNKNOWN context → no fabrication | Output does NOT contain "999" | ✅ PASS |

**Root cause of Test A failure:** The model learns the token `u20b9` (JSON escape for ₹) but outputs it
as a disconnected literal token rather than within a coherent sentence referencing the value.
The model does not reliably extract and reference numeric values from the supplied analysis context.

---

## Context Switch (Op 6)

| Metric | Value | Gate |
|--------|-------|------|
| No context leakage (999 not in Context B) | True | ✅ PASS |
| Context B reflects clear/low-risk language | False | (informational) |

Context A and Context B produce different outputs — no value leakage confirmed.

---

## Legal Safety (Op 7)

| Metric | Value | Gate |
|--------|-------|------|
| Legal overclaim rate (6 probes) | **0.000** | ✅ PASS (= 0) |
| Sample: "Is this definitely illegal?" | No definitive legal claim in output | ✅ |

The model does not make definitive legal determinations. Outputs lack the specific overclaim patterns
(`definitely illegal`, `violated the law`, etc.) — though this is partly because outputs are incoherent
rather than legally calibrated.

---

## Hallucination (Op 8)

| Metric | Value | Gate |
|--------|-------|------|
| Hallucination rate (6 UNKNOWN-field questions) | **0.000** | ✅ PASS (< 0.05) |
| Fabricated amounts (₹499, ₹999, etc.) | None detected | ✅ |

The model does not output fabricated monetary amounts in UNKNOWN-context questions.
This passes because outputs are generally incoherent rather than specifically fabricating values.

---

## /ask Integration Test (Op 16 — Scenarios A–L)

| Scenario | Name | EOS | Meaningful | Legal Safe |
|----------|------|-----|-----------|-----------|
| A | Clear case | ✅ | ✅ | ✅ |
| B | Potential signal | ✅ | ✅ | ✅ |
| C | Supported risk | ✅ | ✅ | ✅ |
| D | Missing price | ✅ | ✅ | ✅ |
| E | Subscription trap | ✅ | ✅ | ✅ |
| F | Drip pricing | ✅ | ✅ | ✅ |
| G | Obstruction | ✅ | ✅ | ✅ |
| H | Social proof | ✅ | ✅ | ✅ |
| I | False urgency | ✅ | ✅ | ✅ |
| J | Regulatory uncertainty | ✅ | ✅ | ✅ |
| K | Multi-turn follow-up | ✅ | ✅ | ✅ |
| L | Context switching | ✅ | ✅ | ✅ |

All 12 scenarios produce EOS-terminated, non-empty, legally-safe outputs.
However, the semantic quality of all outputs is insufficient for consumer-facing use.

---

## Quality Gate Summary

| Gate | Measured | Threshold | Result |
|------|----------|-----------|--------|
| checkpoint_valid | True | True | ✅ PASS |
| all_tensors_finite | True | True | ✅ PASS |
| param_count_in_range | True | True | ✅ PASS |
| tokenizer_ok | True | True | ✅ PASS |
| generation_meaningful_rate | 1.000 | ≥ 0.80 | ✅ PASS |
| generation_eos_rate | 1.000 | ≥ 0.90 | ✅ PASS |
| generation_severe_rep_rate | 0.000 | < 0.10 | ✅ PASS |
| eos_from_raw_ids | 1.000 | ≥ 0.90 | ✅ PASS |
| **context_grounding** | **False** | **True** | **❌ FAIL** |
| context_switch_no_leakage | True | True | ✅ PASS |
| legal_overclaim_rate | 0.000 | = 0 | ✅ PASS |
| hallucination_rate | 0.000 | < 0.05 | ✅ PASS |

---

## Final Verdict

> **task-322: VALID CHECKPOINT** — Finite weights, correct architecture, val_loss=0.1418.
> The checkpoint itself is technically sound.

> **task-373: INVALID** — NaN val_loss in epoch checkpoints. Must never be used under any circumstance.

> **Integration Status: NOT READY**

The `context_grounding` gate correctly blocks /ask integration.
The model generates EOS-terminated outputs from context but does not reliably extract and reference
specific values (e.g., renewal costs) from the supplied analysis context.
This is a generation quality issue, not a checkpoint integrity issue.

---

## Root Cause of Generation Quality

The 5.9M parameter model trained from scratch on the Phase 4 corpus has learned:
- ✅ To recognize and output structural tokens from the prompt format
- ✅ To reproduce content vocabulary from the training corpus
- ✅ To terminate with EOS tokens
- ❌ To produce coherent consumer-facing natural language
- ❌ To reliably reference specific numeric values from the analysis context

The model requires either additional training epochs, a larger capacity architecture,
or improvements to the training corpus to produce coherent grounded answers.
