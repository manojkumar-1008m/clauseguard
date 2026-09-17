# NaN Gate Regression Report
# Phase 4.4

---

## Summary

task-373 reported **READY FOR /ask INTEGRATION** despite:
- Training loss = NaN from step 25
- Validation loss = NaN for all epochs
- Resulting model weights: VALID (random init — never updated by NaN gradient)

This was a **critical gate defect**. The pipeline incorrectly declared the run READY.

---

## Verified Checkpoint States

| File | Run | Val Loss | Weights | Status |
|------|-----|----------|---------|--------|
| `best.pt` | task-322 | **0.1418** | Finite | ✅ VALID |
| `epoch_1.pt` | task-373 | **NaN** | Finite (random) | ❌ INVALID |
| `epoch_2.pt` | task-373 | **NaN** | Finite (random) | ❌ INVALID |

**Note:** task-373 weights are finite (not NaN) because NaN loss → NaN gradient →
`clip_grad_norm_` clamps to 1.0 → weights update by 0 (or near-0). The model
stays at its random initialization, producing garbage outputs but passing
`torch.isfinite()` checks.

---

## Root Cause Analysis

### RC-1 — Checkpoint save condition
**Code:** `if v_loss < best_val_loss: best_val_loss = v_loss`

**Problem:** In IEEE 754, `NaN < math.inf` evaluates to **False**.
So `best_val_loss` remained `math.inf` throughout all NaN epochs.
`best.pt` was never overwritten during task-373, which is why the task-322 checkpoint survived.

**Fix applied:** `if math.isfinite(v_loss) and v_loss < best_val_loss:`

---

### RC-2 — Training loop did not abort on NaN
**Code:** No NaN check existed between computing loss and calling `.backward()`

**Problem:** When loss is NaN, `.backward()` propagates NaN gradients.
`clip_grad_norm_` then produces a gradient scale of 0/inf → weights receive
effectively-zero updates → model stays at random initialization indefinitely.
The run never terminated early despite producing garbage at every step.

**Fix applied:**
```python
if not math.isfinite(loss.item()):
    training_nan_detected = True
    epoch_nan = True
    break  # abort epoch immediately
```

---

### RC-3 — Gate did not check training/validation loss finiteness
**Code:** Gate evaluated only downstream metrics (meaningful_rate, eos_rate, etc.)

**Problem:** A random-weight model can accidentally satisfy token-level metrics:
- `meaningful_answer_rate`: passes if output length > 10 chars (random model outputs random tokens)
- `eos_completion_rate`: passes if `</answer>` appears anywhere in output
- `repetition_rate`: may pass if outputs are varied (random sampling)
- `hallucination_rate`: passes if fabricated amounts are not detected (random model doesn't fabricate coherently)
- `legal_overclaim_rate`: passes if specific overclaim phrases don't appear

**Collectively:** A random-weight model can satisfy ≥ 80% of the existing gates.

**Fix applied:** New gate keys using `math.isfinite()` explicitly:
```python
training_loss_finite = all(math.isfinite(m["train_loss"]) for m in epoch_metrics) and not training_nan_detected
validation_loss_finite = all(math.isfinite(m["val_loss"]) for m in epoch_metrics) and math.isfinite(best_val_loss)
checkpoint_finite = _verify_model_finite(model)  # checks every float tensor
micro_overfit_passed = bool(micro_res.get("passed", False))
```

These are added to `gate` and must ALL be True for `gate_passed = True`.

---

### RC-4 — Micro-overfit failure was not a hard blocker
**Code:** `if not micro_res["passed"]: print("... but continuing")`

**Problem:** When the micro-overfit test fails (NaN initial loss), the pipeline printed a warning
but continued to full training. A failed micro-overfit is a strong signal of a broken training
configuration and should block the pipeline.

**Fix applied:** `micro_overfit_passed` is now a required gate key. A failed micro-overfit
means `gate_passed = False` regardless of downstream evaluation metrics.

---

### RC-5 — No validate_checkpoint() before integration
**Code:** (absent — no checkpoint finiteness check before loading for inference)

**Problem:** Even if all training metrics were NaN, the pipeline could proceed to
/ask integration by loading whatever checkpoint existed on disk.

**Fix applied:** `ClauseGuardDecoderAnswerProvider._load()` calls `validate_checkpoint()`
before loading any checkpoint. If validation fails (NaN/Inf), the provider refuses to
load the model and falls back to `LocalAnswerGenerator`. The `provider` field in
`AskResponse` shows `"local_deterministic_fallback"` when this occurs.

---

## Why task-373 Weights Are Finite But Model Is Invalid

A subtle but important point:

1. NaN loss → NaN gradient at all positions
2. `clip_grad_norm_` computes gradient norm = NaN → clamp produces ≈ 0 update
3. AdamW applies the update: weights += ≈ 0
4. Weights remain at their random initialization (all values finite, ~N(0, 0.02))
5. A randomly-initialized model produces garbage outputs — but they're finite!

This is why:
- `torch.isfinite(param).all()` = True for all task-373 weights
- But the model produces structurally random outputs unrelated to the input context
- The gate must check **training loss finiteness**, not just weight finiteness

---

## The Correct Approach

```
NaN detected anywhere during training
    → training_nan_detected = True
    → gate["training_loss_finite"] = False
    → gate_passed = False
    → status = NOT READY
    → integration BLOCKED
```

This is now implemented in `phase4_training.py`.

---

## Verdicts

| Run | Verdict | Evidence |
|-----|---------|----------|
| **task-322** | ✅ **VALID** | val_loss=0.1418 stored in best.pt; all weights finite; training converged |
| **task-373** | ❌ **INVALID** | val_loss=NaN for all epochs; epoch_1.pt and epoch_2.pt contain random-init weights; must never be used |

> task-373 is **not usable under any circumstance**.
> Its epoch checkpoints (`epoch_1.pt`, `epoch_2.pt`) contain random-initialization weights.
