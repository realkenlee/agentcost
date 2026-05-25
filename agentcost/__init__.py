"""agentcost — token attribution for AI agents."""
from __future__ import annotations
from pathlib import Path

from ._context import label, current_labels  # noqa: F401
from ._log import load_events                # noqa: F401

_initialized = False


def init(log_path: Path | None = None) -> None:
    """Instrument all installed LLM clients. Call once at startup."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    from . import _log, _patch
    _log.setup(log_path)

    patched = []
    if _patch.patch_anthropic():
        patched.append("anthropic")
    if _patch.patch_openai():
        patched.append("openai")
    if _patch.patch_litellm():
        patched.append("litellm")

    if patched:
        print(f"[agentcost] tracking: {', '.join(patched)}")
    else:
        print("[agentcost] no supported LLM client found — install anthropic, openai, or litellm")
