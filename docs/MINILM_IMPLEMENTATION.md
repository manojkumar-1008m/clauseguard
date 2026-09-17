# MiniLM Explanation Layer

ClauseGuard uses `sentence-transformers/all-MiniLM-L6-v2` as an optional CPU
embedding model for semantic evidence ranking. It is not a text generator or a
risk classifier.

The layer runs after `ExplanationContext` is built and after the
`ConsumerRiskGate`. It embeds a query made from verified context fields and
ranks the verified evidence descriptions by cosine similarity. The deterministic
`ConsumerExplanationEngine` remains responsible for every user-facing sentence.

MiniLM is loaded lazily and cached for the process lifetime. Loading is local-only
by default so the API does not depend on network access:

```text
CLAUSEGUARD_MINILM_LOCAL_ONLY=0
```

enables the first-run Hugging Face download. If the package, weights, or
inference are unavailable, the explanation remains deterministic and includes a
`semantic_layer.status` of `fallback`. When upstream marks context as required,
the layer records `insufficient_context` and does not rank or reinterpret it.

The explanation metadata records model name, task, CPU device, load time,
inference time, and process memory when `psutil` is available.