"""ClauseGuard local decoder-only LLM smoke stack.

This package intentionally implements a tiny, real generative Transformer
for CPU-only smoke testing. It is not a replacement for the risk engine.
"""

from .config import ClauseGuardLLMConfig, SmokeTestConfig
from .dataset import ClauseGuardQADataset
from .model import ClauseGuardDecoderLM
from .tokenizer import ClauseGuardTokenizer
from .smoke import run_smoke_test
from .full_training import build_clauseguard_domain_corpus, train_clauseguard_llm_phase2
from .generation import generate_clauseguard_text
from .phase2_training import build_phase2_corpus, split_phase2_corpus, train_phase2
from .phase3_training import build_phase3_corpus, validate_corpus, run_phase3
from .phase4_training import build_phase4_corpus, validate_phase4_corpus, run_phase4
from .phase4_1_training import run_phase4_1
from .phase4_2_diagnostics import run_diagnostics as run_phase4_2_diagnostics
from .phase4_3_repair import run_phase4_3_repair
from .checkpoint_validator import validate_checkpoint, CheckpointVerificationResult
from .phase4_4_verify import run_phase4_4_verify

__all__ = [
    "SmokeTestConfig",
    "ClauseGuardLLMConfig",
    "ClauseGuardQADataset",
    "ClauseGuardDecoderLM",
    "ClauseGuardTokenizer",
    "run_smoke_test",
    "build_clauseguard_domain_corpus",
    "train_clauseguard_llm_phase2",
    "generate_clauseguard_text",
    "build_phase2_corpus",
    "split_phase2_corpus",
    "train_phase2",
    "build_phase3_corpus",
    "validate_corpus",
    "run_phase3",
    "build_phase4_corpus",
    "validate_phase4_corpus",
    "run_phase4",
    "run_phase4_1",
    "run_phase4_2_diagnostics",
    "run_phase4_3_repair",
    "validate_checkpoint",
    "CheckpointVerificationResult",
    "run_phase4_4_verify",
]
