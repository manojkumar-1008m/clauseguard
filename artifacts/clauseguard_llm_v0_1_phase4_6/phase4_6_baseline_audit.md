# Phase 4.6 — Baseline /ask & Checkpoint Integrity Audit

**Date:** 2026-09-14  
**Audit Target:** `backend/services/ask_clauseguard.py` and `backend/main.py`  
**Model:** ClauseGuardDecoderLM-v0.1 (task-322 / Phase 4.5)  

---

## 1. Checkpoint & Artifact Verification

| Property | Value | Integrity Verification |
|---|---|---|
| **Checkpoint Path** | `C:\Users\rog\Downloads\clauseguard_zipped\clauseguard\artifacts\clauseguard_llm_v0_1_phase4_5\checkpoints\best.pt` | Exists, verified |
| **SHA-256** | `2f8b756bcf4438c2add273a9e4db5f5009d977908a9af9390707c1563013dccd` | Verified |
| **File Size** | 23,572,281 bytes | Uncorrupted |
| **Tokenizer Path** | `C:\Users\rog\Downloads\clauseguard_zipped\clauseguard\artifacts\clauseguard_llm_v0_1_phase4_5\tokenizer\tokenizer.json` | Exists, verified |
| **Tokenizer SHA-256** | `803434c63f3809247ec88a9e6366e4f94b303b015654b80ae0db3aca4aaf6e5c` | Verified Phase 4.5 vocabulary |
| **task-322 Original** | `artifacts/clauseguard_llm_v0_1_phase4/checkpoints/best.pt` | Untouched (`79d7f1974fc12f92...`) |

---

## 2. Tensor & Parameter Integrity

| Metric | Target | Actual | Status |
|---|---|---|---|
| **Parameter Count** | 5,885,952 | 5,885,952 | **PASS** |
| **NaN Count** | 0 | 0 | **PASS** |
| **Inf Count** | 0 | 0 | **PASS** |
| **Validation Loss** | Finite float | 0.188820 | **PASS** |
| **All Tensors Finite** | True | True | **PASS** |
| **validate_checkpoint()** | Valid | True | **PASS** |

---

## 3. /ask Architecture & Contract Compliance

1. **Active Provider:** `ClauseGuardDecoderAnswerProvider` with `LocalAnswerGenerator` fallback.
2. **External LLM Calls:** **ZERO** (No OpenAI, Anthropic, Gemini, or external API keys).
3. **Pretrained Weights:** **ZERO** (Model was initialized and trained strictly from scratch).
4. **Authority Boundary:** The LLM only generates consumer-facing explanatory answers; it has **no authority** over `risk_score`, `risk_level`, `gate_decision`, or `detected_patterns`.
5. **Context Grounding Serialization:** `_context_to_phase45_dict()` formats canonical analysis into uppercase `<ANALYSIS>...</ANALYSIS>` and `<QUESTION>...</QUESTION>` without raw JSON leakage or dangling answer tags.
6. **Graceful Fallback:** If checkpoint loading fails validation or files are missing, `ClauseGuardDecoderAnswerProvider` safely routes to `LocalAnswerGenerator` and marks `fallback_used=True` with `provider="local_deterministic_fallback"`.

---

## 4. Audit Verdict

**PASS** — The baseline architecture is fully validated, the Phase 4.5 model weights are intact and verified finite, and the integration layer meets all security, safety, and traceability constraints.
