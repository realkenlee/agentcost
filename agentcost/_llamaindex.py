"""LlamaIndex callback handler."""
from __future__ import annotations
from typing import Any, Optional

from . import _context, _git, _log, _pricing


def _record(model: str, input_tokens: int, output_tokens: int) -> None:
    _log.record(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_pricing.cost_usd(model, input_tokens, output_tokens),
        labels=_context.current_labels(),
        git=_git.get_context(),
        latency_ms=None,
    )


def patch_llamaindex() -> bool:
    try:
        from llama_index.core.callbacks.base_handler import BaseCallbackHandler  # type: ignore
        from llama_index.core.callbacks.schema import CBEventType, EventPayload  # type: ignore
        from llama_index.core import Settings  # type: ignore
    except ImportError:
        return False

    class AgentCostCallbackHandler(BaseCallbackHandler):
        def __init__(self) -> None:
            super().__init__(event_starts_to_ignore=[], event_ends_to_ignore=[])

        def on_event_start(self, event_type: CBEventType, payload: Optional[dict] = None,
                           event_id: str = "", **kwargs: Any) -> str:
            return event_id

        def on_event_end(self, event_type: CBEventType, payload: Optional[dict] = None,
                         event_id: str = "", **kwargs: Any) -> None:
            if event_type != CBEventType.LLM or not payload:
                return
            try:
                response = payload.get(EventPayload.RESPONSE)
                if response is None:
                    return
                # LlamaIndex wraps the raw provider response
                raw = getattr(response, "raw", None) or {}
                if hasattr(raw, "usage"):
                    u = raw.usage
                    _record(
                        model=getattr(raw, "model", "unknown"),
                        input_tokens=getattr(u, "prompt_tokens", 0),
                        output_tokens=getattr(u, "completion_tokens", 0),
                    )
                elif isinstance(raw, dict) and "usage" in raw:
                    u = raw["usage"]
                    _record(
                        model=raw.get("model", "unknown"),
                        input_tokens=u.get("prompt_tokens", 0),
                        output_tokens=u.get("completion_tokens", 0),
                    )
            except Exception:
                pass

        def start_trace(self, trace_id: Optional[str] = None) -> None:
            pass

        def end_trace(self, trace_id: Optional[str] = None,
                      trace_map: Optional[dict] = None) -> None:
            pass

    try:
        handler = AgentCostCallbackHandler()
        Settings.callback_manager.add_handler(handler)
        return True
    except Exception:
        return False
