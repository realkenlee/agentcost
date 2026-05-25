"""Claude Code integration — reads session JSONL logs and registers hooks."""
from __future__ import annotations
import json
import os
from pathlib import Path


PROJECTS_DIR = Path.home() / ".claude" / "projects"
SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


def find_latest_jsonl() -> Path | None:
    """Return the most recently modified JSONL in ~/.claude/projects/."""
    if not PROJECTS_DIR.exists():
        return None
    jsonls = sorted(PROJECTS_DIR.rglob("*.jsonl"), key=os.path.getmtime, reverse=True)
    return jsonls[0] if jsonls else None


def extract_session_usage(jsonl_path: Path) -> dict:
    """Sum token usage from a Claude Code conversation JSONL."""
    input_tokens = 0
    output_tokens = 0
    model = "unknown"
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                msg = obj.get("message", {})
                # Token usage lives in the assistant message
                usage = msg.get("usage") or {}
                input_tokens  += usage.get("input_tokens", 0)
                output_tokens += usage.get("output_tokens", 0)
                if msg.get("model"):
                    model = msg["model"]
            except (json.JSONDecodeError, AttributeError):
                continue
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "model": model}


def install_hooks() -> bool:
    """Add agentcost Stop hook to ~/.claude/settings.json."""
    settings: dict = {}
    if SETTINGS_PATH.exists():
        try:
            settings = json.loads(SETTINGS_PATH.read_text())
        except json.JSONDecodeError:
            pass

    hooks = settings.setdefault("hooks", {})
    stop_hooks: list = hooks.setdefault("Stop", [])

    hook_cmd = "agentcost record-session"
    for entry in stop_hooks:
        for h in entry.get("hooks", []):
            if h.get("command") == hook_cmd:
                return False  # already installed

    stop_hooks.append({
        "matcher": "",
        "hooks": [{"type": "command", "command": hook_cmd}],
    })

    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
    return True


def uninstall_hooks() -> bool:
    """Remove agentcost hooks from ~/.claude/settings.json."""
    if not SETTINGS_PATH.exists():
        return False
    settings = json.loads(SETTINGS_PATH.read_text())
    hooks = settings.get("hooks", {})
    stop_hooks = hooks.get("Stop", [])
    before = len(stop_hooks)
    hooks["Stop"] = [
        e for e in stop_hooks
        if not any(h.get("command") == "agentcost record-session"
                   for h in e.get("hooks", []))
    ]
    if len(hooks["Stop"]) == before:
        return False
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
    return True
