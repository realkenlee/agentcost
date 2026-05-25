"""LangChain + CrewAI callback handler. CrewAI is built on LangChain — same handler works."""
from __future__ import annotations
from typing import Any
from uuid import UUID

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


def make_callback():
    """Return an AgentCostCallbackHandler instance, or None if langchain not installed."""
    try:
        from langchain_core.callbacks.base import BaseCallbackHandler
        from langchain_core.outputs import LLMResult
    except ImportError:
        try:
            from langchain.callbacks.base import BaseCallbackHandler  # type: ignore
            from langchain.schema import LLMResult  # type: ignore
        except ImportError:
            return None

    class AgentCostCallbackHandler(BaseCallbackHandler):
        def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
            try:
                llm_output = response.llm_output or {}
                usage = (
                    llm_output.get("token_usage")
                    or llm_output.get("usage")
                    or {}
                )
                model = llm_output.get("model_name", "unknown")
                _record(
                    model=model,
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                )
            except Exception:
                pass

    return AgentCostCallbackHandler()


def patch_langchain() -> bool:
    """Register agentcost as a global LangChain callback — applies to all chains."""
    handler = make_callback()
    if handler is None:
        return False
    try:
        from langchain_core.callbacks import get_callback_manager  # type: ignore
        get_callback_manager().add_handler(handler, inherit=True)
        return True
    except Exception:
        pass
    try:
        # Older LangChain
        import langchain  # type: ignore
        if not hasattr(langchain, "callbacks"):
            langchain.callbacks = []
        langchain.callbacks.append(handler)
        return True
    except Exception:
        return False
