from dataclasses import dataclass


@dataclass
class SmokeTestConfig:
    vocab_size: int = 2048
    context_length: int = 128
    embedding_dim: int = 128
    num_layers: int = 2
    num_heads: int = 4
    feedforward_dim: int = 512
    dropout: float = 0.1
    batch_size: int = 2
    learning_rate: float = 3e-4
    device: str = "cpu"

    @property
    def model_name(self) -> str:
        return "ClauseGuard-LLM-v0.1-smoke"


@dataclass
class ClauseGuardLLMConfig:
    vocab_size: int = 4096
    context_length: int = 384
    embedding_dim: int = 256
    num_layers: int = 6
    num_heads: int = 4
    feedforward_dim: int = 1024
    dropout: float = 0.1
    batch_size: int = 2
    gradient_accumulation_steps: int = 4
    learning_rate: float = 3e-4
    device: str = "cpu"
    tie_weights: bool = True
    domain_name: str = "ClauseGuard-LLM-v0.1"

    @property
    def model_name(self) -> str:
        return "ClauseGuard-LLM-v0.1"

    def estimate_parameters(self) -> dict:
        from .hardware import estimate_parameter_count
        return estimate_parameter_count(
            vocab_size=self.vocab_size,
            context_length=self.context_length,
            embedding_dim=self.embedding_dim,
            num_layers=self.num_layers,
            num_heads=self.num_heads,
            feedforward_dim=self.feedforward_dim,
            tie_weights=self.tie_weights,
        )
