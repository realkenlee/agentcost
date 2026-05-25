"""ContextVar-based label propagation — works across sync and async code."""
from __future__ import annotations
import contextvars
from contextlib import contextmanager
from typing import Any

_labels: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar(
    "agentcost_labels", default={}
)


def current_labels() -> dict[str, str]:
    return dict(_labels.get())


@contextmanager
def label(**kwargs: Any):
    """Attach labels to all LLM calls within this block.

    with label(pr="1234", team="platform"):
        client.messages.create(...)   # attributed to pr=1234, team=platform
    """
    merged = {**_labels.get(), **{k: str(v) for k, v in kwargs.items()}}
    token = _labels.set(merged)
    try:
        yield
    finally:
        _labels.reset(token)
