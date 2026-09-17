# Phase 4.1 Artifacts

CPU_FAST uses pre-tokenized cached tensors, controlled CPU threads, batched generation, and resumable checkpoints. Quality gates are unchanged. Stage A is one epoch; Stage B resumes from `checkpoints/stage_a.pt`.
