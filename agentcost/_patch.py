"""Monkey-patch Anthropic and OpenAI SDK clients to capture token usage."""
from __future__ import annotations
import time
from typing import Any

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


def patch_anthropic() -> bool:
    try:
        import anthropic

        original_create = anthropic.resources.messages.Messages.create

        def _create(self, *args: Any, **kwargs: Any) -> Any:
            t0 = time.monotonic()
            response = original_create(self, *args, **kwargs)
            ms = int((time.monotonic() - t0) * 1000)
            try:
                u = response.usage
                _record(response.model, u.input_tokens, u.output_tokens, ms)
            except Exception:
                pass
            return response

        async def _acreate(self, *args: Any, **kwargs: Any) -> Any:
            t0 = time.monotonic()
            response = await original_create.__wrapped__(self, *args, **kwargs) \
                if hasattr(original_create, "__wrapped__") \
                else await anthropic.resources.messages.AsyncMessages.create(self, *args, **kwargs)
            ms = int((time.monotonic() - t0) * 1000)
            try:
                u = response.usage
                _record(response.model, u.input_tokens, u.output_tokens, ms)
            except Exception:
                pass
            return response

        anthropic.resources.messages.Messages.create = _create

        # Async client
        original_acreate = anthropic.resources.messages.AsyncMessages.create

        async def _async_create(self, *args: Any, **kwargs: Any) -> Any:
            t0 = time.monotonic()
            response = await original_acreate(self, *args, **kwargs)
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


def patch_openai() -> bool:
    try:
        import openai

        original_create = openai.resources.chat.completions.Completions.create

        def _create(self, *args: Any, **kwargs: Any) -> Any:
            t0 = time.monotonic()
            response = original_create(self, *args, **kwargs)
            ms = int((time.monotonic() - t0) * 1000)
            try:
                u = response.usage
                _record(response.model, u.prompt_tokens, u.completion_tokens, ms)
            except Exception:
                pass
            return response

        openai.resources.chat.completions.Completions.create = _create

        original_acreate = openai.resources.chat.completions.AsyncCompletions.create

        async def _async_create(self, *args: Any, **kwargs: Any) -> Any:
            t0 = time.monotonic()
            response = await original_acreate(self, *args, **kwargs)
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
                    model = kwargs.get("model", "unknown")
                    _record(model, u.prompt_tokens, u.completion_tokens, ms)
                except Exception:
                    pass

            async def async_log_success_event(
                self, kwargs: dict, response_obj: Any, start_time: Any, end_time: Any
            ) -> None:
                self.log_success_event(kwargs, response_obj, start_time, end_time)

        if not isinstance(getattr(litellm, "callbacks", None), list):
            litellm.callbacks = []
        litellm.callbacks.append(_Callback())
        return True
    except (ImportError, AttributeError):
        return False
