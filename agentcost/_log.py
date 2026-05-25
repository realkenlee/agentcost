"""Local JSONL event log — ~/.agentcost/events.jsonl"""
from __future__ import annotations
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()
_log_path: Path | None = None


def setup(path: Path | None = None) -> None:
    global _log_path
    _log_path = path or Path.home() / ".agentcost" / "events.jsonl"
    _log_path.parent.mkdir(parents=True, exist_ok=True)


def record(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float | None,
    labels: dict[str, str],
    git: dict[str, str],
    latency_ms: int | None = None,
) -> None:
    if _log_path is None:
        return
    event = {
        "ts":            datetime.now(timezone.utc).isoformat(),
        "model":         model,
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "cost_usd":      cost_usd,
        "latency_ms":    latency_ms,
        **{f"label_{k}": v for k, v in labels.items()},
        **{f"git_{k}": v for k, v in git.items()},
    }
    line = json.dumps(event, separators=(",", ":"))
    with _lock:
        with open(_log_path, "a") as f:
            f.write(line + "\n")


def load_events(path: Path | None = None) -> list[dict]:
    p = path or _log_path or Path.home() / ".agentcost" / "events.jsonl"
    if not p.exists():
        return []
    events = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events
