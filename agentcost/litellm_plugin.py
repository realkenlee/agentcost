"""
LiteLLM named plugin — enables `success_callback: ["agentcost"]` in litellm_config.yaml.

Gateway users add one line to their existing LiteLLM proxy config:

  litellm_settings:
    success_callback: ["agentcost"]

Label calls with metadata:
  litellm.completion(model="...", metadata={"team": "platform", "pr": "1234"})

Or via proxy request headers (X-Cost-Team, X-Cost-PR, etc.) — handled by the proxy layer.
"""
from __future__ import annotations
from typing import Any
from datetime import datetime

from . import _git, _log, _pricing


class AgentCostLogger:
    """LiteLLM CustomLogger interface."""

    def log_success_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        self._record(kwargs, response_obj, start_time, end_time)

    async def async_log_success_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        self._record(kwargs, response_obj, start_time, end_time)

    def log_stream_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        self._record(kwargs, response_obj, start_time, end_time)

    def _record(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        try:
            u = response_obj.usage
            ms = int((end_time - start_time).total_seconds() * 1000)
            model = kwargs.get("model", "unknown")

            # Labels from litellm metadata
            meta: dict = kwargs.get("metadata") or kwargs.get("litellm_params", {}).get("metadata") or {}
            labels = {
                k: str(v) for k, v in meta.items()
                if k in ("team", "pr", "user", "branch", "env", "project", "service")
            }

            # Labels from proxy headers (passed through litellm metadata)
            header_map = {
                "x-cost-team":   "team",
                "x-cost-pr":     "pr",
                "x-cost-user":   "user",
                "x-cost-branch": "branch",
            }
            headers = meta.get("headers") or {}
            for header, label in header_map.items():
                if header in headers:
                    labels.setdefault(label, headers[header])

            _log.record(
                model=model,
                input_tokens=getattr(u, "prompt_tokens", 0),
                output_tokens=getattr(u, "completion_tokens", 0),
                cost_usd=_pricing.cost_usd(
                    model,
                    getattr(u, "prompt_tokens", 0),
                    getattr(u, "completion_tokens", 0),
                ),
                labels=labels,
                git=_git.get_context(),
                latency_ms=ms,
            )
        except Exception:
            pass


# LiteLLM discovers this via the module-level `logger` attribute
logger = AgentCostLogger()
