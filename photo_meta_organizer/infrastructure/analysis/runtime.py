"""Is the optional ``ai`` extra installed? (``onnxruntime`` and ``tokenizers``)"""

from importlib.util import find_spec


def ai_runtime_installed() -> bool:
    """Whether the packages the AI features run on can be imported, without importing them."""
    return all(find_spec(name) is not None for name in ("onnxruntime", "tokenizers"))
