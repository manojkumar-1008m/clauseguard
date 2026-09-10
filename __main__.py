# __main__.py
"""Compatibility shim for loading the ClauseGuard model.
The original model was serialized from a notebook where a custom
function `production_preprocessor` lived in the notebook's `__main__`
namespace. During deserialization Python attempts to import that
function from a module named `__main__`. Providing this shim ensures
the attribute is available, preventing `AttributeError`.
"""

import re

def production_preprocessor(text: str) -> str:
    """Minimal preprocessing that mirrors typical TF‑IDF preparation.
    - Strip leading/trailing whitespace
    - Collapse consecutive whitespace characters into a single space
    - Return the cleaned string.
    """
    cleaned = text.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned
