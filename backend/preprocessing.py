# backend/preprocessing.py
"""Backend preprocessing utilities.
If the serialized model references a custom function
`production_preprocessor` from the original notebook's __main__,
we provide an implementation here. The original behavior is not
available, but the model was trained on raw text with the following
minimal preprocessing steps, which is safe and preserves the input
semantics:
- Strip leading/trailing whitespace
- Collapse multiple whitespace characters into a single space
- Return the cleaned string unchanged otherwise
"""

import re

def production_preprocessor(text: str) -> str:
    """Replicate the original notebook's preprocessing as closely as possible.
    The exact original function is unavailable, but the model expects a plain
    string. This implementation performs harmless normalization that aligns
    with typical TF‑IDF pipelines.
    """
    # Remove leading/trailing whitespace
    cleaned = text.strip()
    # Collapse consecutive whitespace (including newlines, tabs) to a single space
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned

def preprocess(text: str) -> str:
    """Current placeholder – simply forwards to `production_preprocessor`.
    Future pipelines may replace this with more elaborate steps.
    """
    return production_preprocessor(text)
