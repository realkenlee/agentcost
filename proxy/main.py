"""
agentcost proxy — OpenAI + Anthropic compatible, transparent forwarding with token attribution.

Segment 1 (Claude Code / Codex): set base_url once, every session auto-tracked.
  ANTHROPIC_BASE_URL=http://localhost:8080/anthropic
  OPENAI_BASE_URL=http://localhost:8080/openai

Segment 2 (Gateway): deploy in front of existing LiteLLM/custom proxy.
  Label calls via headers: X-Cost-Team, X-Cost-PR, X-Cost-User, X-Cost-Branch, X-Cost-Env
  Or register API keys in agentcost-keys.yaml: sk-platform-prod → {team: Platform}
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, AsyncGenerator

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

sys.path.insert(0, str(Path(__file__).parent.parent))
from agentcost import _log, _pricing, _git

_log.setup()

app = FastAPI(title="agentcost proxy")

_ANTHROPIC_API = os.environ.get("AGENTCOST_ANTHROPIC_UPSTREAM", "https://api.anthropic.com")
_OPENAI_API    = os.environ.get("AGENTCOST_OPENAI_UPSTREAM",    "https://api.openai.com")

# ── API key → team registry ───────────────────────────────────────────────────

_KEY_MAP: dict[str, dict[str, str]] = {}

_keys_file = os.environ.get("AGENTCOST_KEYS_FILE", "agentcost-keys.yaml")
if Path(_keys_file).exists():
    try:
        import yaml  # type: ignore
        _KEY_MAP = yaml.safe_load(Path(_keys_file).read_text()).get("keys", {})
    except Exception as e:
        print(f"[proxy] keys file error: {e}")

for entry in os.environ.get("AGENTCOST_KEY_MAP", "").split(","):
    if "=" in entry:
        k, v = entry.split("=", 1)
        _KEY_MAP[k.strip()] = {"team": v.strip()}


def _extract_labels(request: Request) -> dict[str, str]:
    labels: dict[str, str] = {}
    for header, label in {
        "x-cost-team": "team", "x-cost-pr": "pr",
        "x-cost-user": "user", "x-cost-branch": "branch", "x-cost-env": "env",
    }.items():
        if val := request.headers.get(header):
            labels[label] = val

    key = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    for k, v in _KEY_MAP.get(key, {}).items():
        labels.setdefault(k, v)

    return labels


def _record_usage(model: str, input_tokens: int, output_tokens: int,
                  labels: dict, ms: int) -> None:
    _log.record(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_pricing.cost_usd(model, input_tokens, output_tokens),
        labels=labels,
        git=_git.get_context(),
        latency_ms=ms,
    )


# ── Streaming support ─────────────────────────────────────────────────────────

async def _stream_anthropic(
    upstream_response: httpx.Response, labels: dict, t0: float
) -> AsyncGenerator[bytes, None]:
    """Forward SSE stream, capture usage from message_start + message_delta events."""
    input_tokens = 0
    output_tokens = 0
    model = "unknown"

    async for line in upstream_response.aiter_lines():
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                event_type = data.get("type", "")
                if event_type == "message_start":
                    msg = data.get("message", {})
                    model = msg.get("model", model)
                    u = msg.get("usage", {})
                    input_tokens = u.get("input_tokens", 0)
                elif event_type == "message_delta":
                    u = data.get("usage", {})
                    output_tokens = u.get("output_tokens", 0)
            except (json.JSONDecodeError, KeyError):
                pass
        yield (line + "\n").encode()

    ms = int((time.monotonic() - t0) * 1000)
    if input_tokens or output_tokens:
        _record_usage(model, input_tokens, output_tokens, labels, ms)


async def _stream_openai(
    upstream_response: httpx.Response, labels: dict, t0: float
) -> AsyncGenerator[bytes, None]:
    """Forward SSE stream, capture usage from final chunk (include_usage=True)."""
    model = "unknown"

    async for line in upstream_response.aiter_lines():
        if line.startswith("data: ") and line != "data: [DONE]":
            try:
                chunk = json.loads(line[6:])
                if chunk.get("model"):
                    model = chunk["model"]
                usage = chunk.get("usage")
                if usage:
                    ms = int((time.monotonic() - t0) * 1000)
                    _record_usage(
                        model,
                        usage.get("prompt_tokens", 0),
                        usage.get("completion_tokens", 0),
                        labels, ms,
                    )
            except (json.JSONDecodeError, KeyError):
                pass
        yield (line + "\n").encode()


# ── Core forwarding ───────────────────────────────────────────────────────────

async def _forward(request: Request, target_base: str, strip_prefix: str,
                   provider: str) -> Response:
    path = request.url.path.removeprefix(strip_prefix)
    url  = f"{target_base}{path}"
    if request.url.query:
        url += f"?{request.url.query}"

    body_bytes = await request.body()
    labels = _extract_labels(request)

    # For OpenAI streaming: inject include_usage so we get tokens in the stream
    is_stream = False
    if provider == "openai" and body_bytes:
        try:
            body_json = json.loads(body_bytes)
            if body_json.get("stream"):
                is_stream = True
                body_json.setdefault("stream_options", {})["include_usage"] = True
                body_bytes = json.dumps(body_json).encode()
        except (json.JSONDecodeError, KeyError):
            pass

    if provider == "anthropic" and body_bytes:
        try:
            body_json = json.loads(body_bytes)
            is_stream = body_json.get("stream", False)
        except json.JSONDecodeError:
            pass

    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length")}

    t0 = time.monotonic()

    if is_stream:
        async def _iter() -> AsyncGenerator[bytes, None]:
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream(
                    method=request.method, url=url,
                    headers=headers, content=body_bytes,
                ) as resp:
                    if provider == "anthropic":
                        async for chunk in _stream_anthropic(resp, labels, t0):
                            yield chunk
                    else:
                        async for chunk in _stream_openai(resp, labels, t0):
                            yield chunk

        return StreamingResponse(_iter(), media_type="text/event-stream")

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.request(
            method=request.method, url=url,
            headers=headers, content=body_bytes,
        )

    ms = int((time.monotonic() - t0) * 1000)

    try:
        data = resp.json()
        u = data.get("usage", {})
        model = data.get("model", "unknown")
        if "input_tokens" in u:      # Anthropic
            _record_usage(model, u["input_tokens"], u["output_tokens"], labels, ms)
        elif "prompt_tokens" in u:   # OpenAI
            _record_usage(model, u["prompt_tokens"], u["completion_tokens"], labels, ms)
    except Exception:
        pass

    return Response(content=resp.content, status_code=resp.status_code,
                    headers=dict(resp.headers))


# ── Routes ────────────────────────────────────────────────────────────────────

@app.api_route("/anthropic/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def anthropic_proxy(request: Request) -> Response:
    return await _forward(request, _ANTHROPIC_API, "/anthropic", "anthropic")


@app.api_route("/openai/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def openai_proxy(request: Request) -> Response:
    return await _forward(request, _OPENAI_API, "/openai", "openai")


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "keys_registered": len(_KEY_MAP),
            "anthropic_upstream": _ANTHROPIC_API, "openai_upstream": _OPENAI_API}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
