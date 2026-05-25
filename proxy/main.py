"""
agentcost proxy — OpenAI + Anthropic compatible, transparent forwarding with token attribution.

Set once at infrastructure level:
  ANTHROPIC_BASE_URL=http://localhost:8080/anthropic
  OPENAI_BASE_URL=http://localhost:8080/openai

Labels come from request headers:
  X-Cost-Team, X-Cost-PR, X-Cost-User, X-Cost-Branch, X-Cost-Env

API key → team registry (agentcost-keys.yaml or AGENTCOST_KEY_MAP env var):
  sk-platform-prod: {team: Platform, env: production}
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

sys.path.insert(0, str(Path(__file__).parent.parent))
from agentcost import _log, _pricing

_log.setup()

app = FastAPI(title="agentcost proxy")

_ANTHROPIC_API = "https://api.anthropic.com"
_OPENAI_API    = "https://api.openai.com"

# Load key → team registry from YAML file or env
_KEY_MAP: dict[str, dict[str, str]] = {}

_keys_file = os.environ.get("AGENTCOST_KEYS_FILE", "agentcost-keys.yaml")
if Path(_keys_file).exists():
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(Path(_keys_file).read_text())
        _KEY_MAP = data.get("keys", {})
    except Exception as e:
        print(f"[proxy] failed to load keys file: {e}")

_key_map_env = os.environ.get("AGENTCOST_KEY_MAP", "")
if _key_map_env:
    for entry in _key_map_env.split(","):
        if "=" in entry:
            k, v = entry.split("=", 1)
            _KEY_MAP[k.strip()] = {"team": v.strip()}


def _extract_labels(request: Request, api_key: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    header_map = {
        "x-cost-team":   "team",
        "x-cost-pr":     "pr",
        "x-cost-user":   "user",
        "x-cost-branch": "branch",
        "x-cost-env":    "env",
    }
    for header, label in header_map.items():
        val = request.headers.get(header)
        if val:
            labels[label] = val

    # API key registry lookup
    key = api_key.lstrip("Bearer ").strip()
    if key in _KEY_MAP:
        for k, v in _KEY_MAP[key].items():
            labels.setdefault(k, v)

    return labels


async def _forward(
    request: Request,
    target_base: str,
    strip_prefix: str,
) -> Response:
    path = request.url.path.removeprefix(strip_prefix)
    url  = f"{target_base}{path}"
    if request.url.query:
        url += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    body = await request.body()
    t0   = time.monotonic()

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body,
        )

    ms = int((time.monotonic() - t0) * 1000)

    # Parse token usage from response
    api_key = request.headers.get("authorization", "")
    labels  = _extract_labels(request, api_key)

    try:
        data = resp.json()
        _try_record(path, data, labels, ms)
    except Exception:
        pass

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
    )


def _try_record(path: str, data: dict, labels: dict[str, str], ms: int) -> None:
    model = data.get("model", "unknown")

    # Anthropic format
    if "usage" in data and "input_tokens" in data.get("usage", {}):
        u = data["usage"]
        _log.record(
            model=model,
            input_tokens=u.get("input_tokens", 0),
            output_tokens=u.get("output_tokens", 0),
            cost_usd=_pricing.cost_usd(model, u.get("input_tokens", 0), u.get("output_tokens", 0)),
            labels=labels,
            git={},
            latency_ms=ms,
        )

    # OpenAI format
    elif "usage" in data and "prompt_tokens" in data.get("usage", {}):
        u = data["usage"]
        _log.record(
            model=model,
            input_tokens=u.get("prompt_tokens", 0),
            output_tokens=u.get("completion_tokens", 0),
            cost_usd=_pricing.cost_usd(model, u.get("prompt_tokens", 0), u.get("completion_tokens", 0)),
            labels=labels,
            git={},
            latency_ms=ms,
        )


# ── Anthropic routes ──────────────────────────────────────────────────────────

@app.api_route("/anthropic/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def anthropic_proxy(request: Request, path: str) -> Response:
    return await _forward(request, _ANTHROPIC_API, "/anthropic")


# ── OpenAI routes ─────────────────────────────────────────────────────────────

@app.api_route("/openai/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def openai_proxy(request: Request, path: str) -> Response:
    return await _forward(request, _OPENAI_API, "/openai")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"ok": True, "keys_registered": len(_KEY_MAP)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
