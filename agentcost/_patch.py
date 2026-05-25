"""Monkey-patch Anthropic and OpenAI SDK clients — handles streaming and non-streaming."""
from __future__ import annotations
import time
from typing import Any, Generator, AsyncGenerator

from . import _context, _git, _log, _pricing


def _record(model: str, input_tokens: int, output_tokens: int, latency_ms: int) -> None:
    _log.record(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_pricing.cost_usd(model, input_tokens, output_tokens),
        labels=_context.current_labels(),
        git=_git.get_context(),
        latency_ms=latency_ms,
    )


# ── Anthropic ─────────────────────────────────────────────────────────────────

def _wrap_anthropic_stream(stream: Any, t0: float) -> Generator:
    """Yield events, capture usage from message_start + message_delta."""
    input_tokens = 0
    output_tokens = 0
    model = "unknown"
    for event in stream:
        event_type = getattr(event, "type", "")
        if event_type == "message_start":
            msg = getattr(event, "message", None)
            if msg:
                model = getattr(msg, "model", model)
                u = getattr(msg, "usage", None)
                if u:
                    input_tokens = getattr(u, "input_tokens", 0)
        elif event_type == "message_delta":
            u = getattr(event, "usage", None)
            if u:
                output_tokens = getattr(u, "output_tokens", 0)
        yield event
    ms = int((time.monotonic() - t0) * 1000)
    try:
        _record(model, input_tokens, output_tokens, ms)
    except Exception:
        pass


async def _wrap_anthropic_stream_async(stream: Any, t0: float) -> AsyncGenerator:
    input_tokens = 0
    output_tokens = 0
    model = "unknown"
    async for event in stream:
        event_type = getattr(event, "type", "")
        if event_type == "message_start":
            msg = getattr(event, "message", None)
            if msg:
                model = getattr(msg, "model", model)
                u = getattr(msg, "usage", None)
                if u:
                    input_tokens = getattr(u, "input_tokens", 0)
        elif event_type == "message_delta":
            u = getattr(event, "usage", None)
            if u:
                output_tokens = getattr(u, "output_tokens", 0)
        yield event
    ms = int((time.monotonic() - t0) * 1000)
    try:
        _record(model, input_tokens, output_tokens, ms)
    except Exception:
        pass


def patch_anthropic() -> bool:
    try:
        import anthropic

        # ── Sync ──
        orig_sync = anthropic.resources.messages.Messages.create

        def _sync_create(self, *args: Any, **kwargs: Any) -> Any:
            t0 = time.monotonic()
            response = orig_sync(self, *args, **kwargs)
            if kwargs.get("stream"):
                return _wrap_anthropic_stream(response, t0)
            ms = int((time.monotonic() - t0) * 1000)
            try:
                u = response.usage
                _record(response.model, u.input_tokens, u.output_tokens, ms)
            except Exception:
                pass
            return response

        anthropic.resources.messages.Messages.create = _sync_create

        # ── Async ──
        orig_async = anthropic.resources.messages.AsyncMessages.create

        async def _async_create(self, *args: Any, **kwargs: Any) -> Any:
            t0 = time.monotonic()
            response = await orig_async(self, *args, **kwargs)
            if kwargs.get("stream"):
                return _wrap_anthropic_stream_async(response, t0)
            ms = int((time.monotonic() - t0) * 1000)
            try:
                u = response.usage
                _record(response.model, u.input_tokens, u.output_tokens, ms)
            except Exception:
                pass
            return response

        anthropic.resources.messages.AsyncMessages.create = _async_create
        return True
    except (ImportError, AttributeError):
        return False


# ── OpenAI ────────────────────────────────────────────────────────────────────

def _wrap_openai_stream(stream: Any, t0: float) -> Generator:
    """Yield chunks; capture usage from final chunk (requires include_usage=True)."""
    model = "unknown"
    for chunk in stream:
        if getattr(chunk, "model", None):
            model = chunk.model
        usage = getattr(chunk, "usage", None)
        if usage:
            ms = int((time.monotonic() - t0) * 1000)
            try:
                _record(model, usage.prompt_tokens, usage.completion_tokens, ms)
            except Exception:
                pass
        yield chunk


async def _wrap_openai_stream_async(stream: Any, t0: float) -> AsyncGenerator:
    model = "unknown"
    async for chunk in stream:
        if getattr(chunk, "model", None):
            model = chunk.model
        usage = getattr(chunk, "usage", None)
        if usage:
            ms = int((time.monotonic() - t0) * 1000)
            try:
                _record(model, usage.prompt_tokens, usage.completion_tokens, ms)
            except Exception:
                pass
        yield chunk


def _inject_usage_in_stream(kwargs: dict) -> None:
    """Auto-inject stream_options so OpenAI returns usage in the stream."""
    if kwargs.get("stream"):
        opts = dict(kwargs.get("stream_options") or {})
        opts["include_usage"] = True
        kwargs["stream_options"] = opts


def patch_openai() -> bool:
    try:
        import openai

        # ── Sync ──
        orig_sync = openai.resources.chat.completions.Completions.create

        def _sync_create(self, *args: Any, **kwargs: Any) -> Any:
            _inject_usage_in_stream(kwargs)
            t0 = time.monotonic()
            response = orig_sync(self, *args, **kwargs)
            if kwargs.get("stream"):
                return _wrap_openai_stream(response, t0)
            ms = int((time.monotonic() - t0) * 1000)
            try:
                u = response.usage
                _record(response.model, u.prompt_tokens, u.completion_tokens, ms)
            except Exception:
                pass
            return response

        openai.resources.chat.completions.Completions.create = _sync_create

        # ── Async ──
        orig_async = openai.resources.chat.completions.AsyncCompletions.create

        async def _async_create(self, *args: Any, **kwargs: Any) -> Any:
            _inject_usage_in_stream(kwargs)
            t0 = time.monotonic()
            response = await orig_async(self, *args, **kwargs)
            if kwargs.get("stream"):
                return _wrap_openai_stream_async(response, t0)
            ms = int((time.monotonic() - t0) * 1000)
            try:
                u = response.usage
                _record(response.model, u.prompt_tokens, u.completion_tokens, ms)
            except Exception:
                pass
            return response

        openai.resources.chat.completions.AsyncCompletions.create = _async_create
        return True
    except (ImportError, AttributeError):
        return False


# ── LiteLLM ───────────────────────────────────────────────────────────────────

def patch_litellm() -> bool:
    try:
        import litellm

        class _Callback:
            def log_success_event(
                self, kwargs: dict, response_obj: Any, start_time: Any, end_time: Any
            ) -> None:
                try:
                    u = response_obj.usage
                    ms = int((end_time - start_time).total_seconds() * 1000)
                    _record(kwargs.get("model", "unknown"), u.prompt_tokens, u.completion_tokens, ms)
                except Exception:
                    pass

            async def async_log_success_event(
                self, kwargs: dict, response_obj: Any, start_time: Any, end_time: Any
            ) -> None:
                self.log_success_event(kwargs, response_obj, start_time, end_time)

            def log_stream_event(self, kwargs: dict, response_obj: Any, start_time: Any, end_time: Any) -> None:
                # LiteLLM fires this at end of stream with accumulated usage
                self.log_success_event(kwargs, response_obj, start_time, end_time)

        if not isinstance(getattr(litellm, "callbacks", None), list):
            litellm.callbacks = []
        litellm.callbacks.append(_Callback())
        return True
    except (ImportError, AttributeError):
        return False
