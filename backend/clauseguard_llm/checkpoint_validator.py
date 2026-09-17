"""checkpoint_validator.py — Phase 4.4 Safe Checkpoint Validation.

Validates a ClauseGuard LLM checkpoint before any integration or inference use.

Rules enforced:
- File must exist and be loadable by torch.load
- checkpoint must contain 'model_state_dict'
- Model architecture must match ClauseGuardLLMConfig
- Parameter count must be in the 5–7 M range
- Every tensor in model_state_dict must be finite (zero NaN, zero Inf)
- Tokenizer file must exist and load successfully
- SHA-256 of the checkpoint file is always recorded

A checkpoint containing NaN or Inf values MUST NEVER be accepted.
math.isfinite() is used explicitly — NaN comparisons must never silently pass.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import torch

from .config import ClauseGuardLLMConfig
from .model import ClauseGuardDecoderLM
from .tokenizer import ClauseGuardTokenizer


@dataclass
class CheckpointVerificationResult:
    """Structured result from validate_checkpoint()."""
    # Identity
    checkpoint_path: str
    file_size_bytes: int
    sha256: str

    # Architecture
    param_count: int
    param_count_in_range: bool           # 5M <= count <= 7M
    config_matches: bool

    # Tensor integrity
    total_tensors: int
    nan_tensor_count: int
    inf_tensor_count: int
    nan_parameter_count: int             # total NaN scalar elements
    inf_parameter_count: int             # total Inf scalar elements
    total_parameter_elements: int
    all_tensors_finite: bool             # nan=0 AND inf=0

    # Tokenizer
    tokenizer_path: str
    tokenizer_ok: bool
    tokenizer_vocab_size: Optional[int]

    # Meta
    checkpoint_epoch: Optional[int]
    checkpoint_val_loss: Optional[float]
    val_loss_finite: bool

    # Final decision
    valid: bool
    failure_reason: Optional[str]
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Checkpoint: {self.checkpoint_path}",
            f"SHA-256: {self.sha256}",
            f"File size: {self.file_size_bytes:,} bytes",
            f"Parameters: {self.param_count:,} (in 5-7M range: {self.param_count_in_range})",
            f"Total tensors: {self.total_tensors}",
            f"NaN tensors: {self.nan_tensor_count} | NaN elements: {self.nan_parameter_count}",
            f"Inf tensors: {self.inf_tensor_count} | Inf elements: {self.inf_parameter_count}",
            f"All tensors finite: {self.all_tensors_finite}",
            f"Tokenizer OK: {self.tokenizer_ok} (vocab={self.tokenizer_vocab_size})",
            f"Checkpoint epoch: {self.checkpoint_epoch}",
            f"Checkpoint val_loss: {self.checkpoint_val_loss} (finite: {self.val_loss_finite})",
            f"Valid: {self.valid}",
        ]
        if self.failure_reason:
            lines.append(f"FAILURE REASON: {self.failure_reason}")
        for note in self.notes:
            lines.append(f"NOTE: {note}")
        return "\n".join(lines)


def _sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_checkpoint(
    checkpoint_path: str | Path,
    config: ClauseGuardLLMConfig | None = None,
    tokenizer_path: str | Path | None = None,
) -> CheckpointVerificationResult:
    """Validate a ClauseGuard LLM checkpoint.

    NEVER returns valid=True if any tensor contains NaN or Inf.
    Uses math.isfinite() explicitly — NaN comparisons never silently pass.

    Args:
        checkpoint_path: Path to the .pt checkpoint file.
        config: Model config to use. If None, uses ClauseGuardLLMConfig().
        tokenizer_path: Path to tokenizer.json. Auto-detected if None.

    Returns:
        CheckpointVerificationResult with full audit details.
    """
    cfg = config or ClauseGuardLLMConfig()
    ckpt_path = Path(checkpoint_path)
    notes: list[str] = []

    # ── Step 1: File existence
    if not ckpt_path.exists():
        return CheckpointVerificationResult(
            checkpoint_path=str(ckpt_path),
            file_size_bytes=0, sha256="", param_count=0, param_count_in_range=False,
            config_matches=False, total_tensors=0, nan_tensor_count=0, inf_tensor_count=0,
            nan_parameter_count=0, inf_parameter_count=0, total_parameter_elements=0,
            all_tensors_finite=False, tokenizer_path="", tokenizer_ok=False,
            tokenizer_vocab_size=None, checkpoint_epoch=None, checkpoint_val_loss=None,
            val_loss_finite=False, valid=False,
            failure_reason=f"Checkpoint file does not exist: {ckpt_path}",
        )

    file_size = ckpt_path.stat().st_size
    sha = _sha256(ckpt_path)

    # ── Step 2: Load checkpoint
    try:
        ckpt = torch.load(str(ckpt_path), map_location="cpu")
    except Exception as exc:
        return CheckpointVerificationResult(
            checkpoint_path=str(ckpt_path), file_size_bytes=file_size, sha256=sha,
            param_count=0, param_count_in_range=False, config_matches=False,
            total_tensors=0, nan_tensor_count=0, inf_tensor_count=0,
            nan_parameter_count=0, inf_parameter_count=0, total_parameter_elements=0,
            all_tensors_finite=False, tokenizer_path="", tokenizer_ok=False,
            tokenizer_vocab_size=None, checkpoint_epoch=None, checkpoint_val_loss=None,
            val_loss_finite=False, valid=False,
            failure_reason=f"torch.load failed: {exc}",
        )

    if "model_state_dict" not in ckpt:
        return CheckpointVerificationResult(
            checkpoint_path=str(ckpt_path), file_size_bytes=file_size, sha256=sha,
            param_count=0, param_count_in_range=False, config_matches=False,
            total_tensors=0, nan_tensor_count=0, inf_tensor_count=0,
            nan_parameter_count=0, inf_parameter_count=0, total_parameter_elements=0,
            all_tensors_finite=False, tokenizer_path="", tokenizer_ok=False,
            tokenizer_vocab_size=None, checkpoint_epoch=ckpt.get("epoch"),
            checkpoint_val_loss=ckpt.get("val_loss"), val_loss_finite=False,
            valid=False, failure_reason="checkpoint missing 'model_state_dict' key",
        )

    state_dict = ckpt["model_state_dict"]
    ckpt_epoch: int | None = ckpt.get("epoch")
    ckpt_val_loss_raw = ckpt.get("val_loss")
    # Explicit isfinite check — never use NaN in a comparison
    if ckpt_val_loss_raw is not None:
        try:
            val_loss_finite = math.isfinite(float(ckpt_val_loss_raw))
        except (TypeError, ValueError):
            val_loss_finite = False
    else:
        val_loss_finite = True  # val_loss absent is not a disqualifier
        notes.append("val_loss key absent from checkpoint")

    # ── Step 3: Load model and verify architecture
    try:
        model = ClauseGuardDecoderLM(cfg)
        model.load_state_dict(state_dict, strict=True)
        config_matches = True
    except Exception as exc:
        config_matches = False
        notes.append(f"load_state_dict failed: {exc}")
        # Still proceed with tensor checks on raw state_dict

    param_count = sum(p.numel() for p in state_dict.values() if isinstance(p, torch.Tensor))
    param_count_in_range = 5_000_000 <= param_count <= 7_000_000
    if not param_count_in_range:
        notes.append(f"Parameter count {param_count:,} outside 5-7M range")

    # ── Step 4: Tensor finiteness — explicit math.isfinite, never NaN comparison
    total_tensors = 0
    nan_tensor_count = 0
    inf_tensor_count = 0
    nan_parameter_count = 0
    inf_parameter_count = 0
    total_parameter_elements = 0

    for name, tensor in state_dict.items():
        if not isinstance(tensor, torch.Tensor):
            continue
        if tensor.dtype not in (torch.float32, torch.float16, torch.bfloat16, torch.float64):
            continue  # skip integer tensors (embedding indices etc.)
        total_tensors += 1
        total_parameter_elements += tensor.numel()
        nan_count = int(tensor.isnan().sum().item())
        inf_count = int(tensor.isinf().sum().item())
        if nan_count > 0:
            nan_tensor_count += 1
            nan_parameter_count += nan_count
            notes.append(f"NaN detected in tensor '{name}': {nan_count} elements")
        if inf_count > 0:
            inf_tensor_count += 1
            inf_parameter_count += inf_count
            notes.append(f"Inf detected in tensor '{name}': {inf_count} elements")

    all_tensors_finite = (nan_parameter_count == 0) and (inf_parameter_count == 0)

    # ── Step 5: Tokenizer check
    if tokenizer_path is None:
        # Auto-detect: sibling tokenizer/ directory
        tok_path = ckpt_path.parent.parent / "tokenizer" / "tokenizer.json"
    else:
        tok_path = Path(tokenizer_path)

    tokenizer_ok = False
    tokenizer_vocab_size = None
    try:
        if tok_path.exists():
            tok = ClauseGuardTokenizer(vocab_size=cfg.vocab_size)
            tok.load(str(tok_path))
            tokenizer_vocab_size = len(tok)
            tokenizer_ok = True
        else:
            notes.append(f"Tokenizer not found at {tok_path}")
    except Exception as exc:
        notes.append(f"Tokenizer load failed: {exc}")

    # ── Final decision
    # CRITICAL: NaN/Inf in any tensor = INVALID, unconditionally
    failure_reason = None
    if not all_tensors_finite:
        failure_reason = (
            f"INVALID CHECKPOINT: {nan_parameter_count} NaN + {inf_parameter_count} Inf "
            f"parameter elements across {nan_tensor_count + inf_tensor_count} tensors. "
            "This checkpoint must never be used."
        )
    elif not config_matches:
        failure_reason = "Model architecture does not match config (load_state_dict failed)"
    elif not param_count_in_range:
        failure_reason = f"Parameter count {param_count:,} outside 5-7M range"
    elif not tokenizer_ok:
        failure_reason = "Tokenizer could not be loaded"

    valid = failure_reason is None

    return CheckpointVerificationResult(
        checkpoint_path=str(ckpt_path),
        file_size_bytes=file_size,
        sha256=sha,
        param_count=param_count,
        param_count_in_range=param_count_in_range,
        config_matches=config_matches,
        total_tensors=total_tensors,
        nan_tensor_count=nan_tensor_count,
        inf_tensor_count=inf_tensor_count,
        nan_parameter_count=nan_parameter_count,
        inf_parameter_count=inf_parameter_count,
        total_parameter_elements=total_parameter_elements,
        all_tensors_finite=all_tensors_finite,
        tokenizer_path=str(tok_path),
        tokenizer_ok=tokenizer_ok,
        tokenizer_vocab_size=tokenizer_vocab_size,
        checkpoint_epoch=ckpt_epoch,
        checkpoint_val_loss=float(ckpt_val_loss_raw) if ckpt_val_loss_raw is not None else None,
        val_loss_finite=val_loss_finite,
        valid=valid,
        failure_reason=failure_reason,
        notes=notes,
    )
