"""agentcost CLI"""
from __future__ import annotations
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ._log import load_events


# ── report ────────────────────────────────────────────────────────────────────

def cmd_report(args: argparse.Namespace) -> None:
    events = load_events()
    if not events:
        print("No events recorded yet. Run `agentcost claude-code install` or add `agentcost.init()` to your code.")
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    events = [e for e in events if datetime.fromisoformat(e["ts"]) >= cutoff]
    if not events:
        print(f"No events in the last {args.days} days.")
        return

    dim = args.by
    groups: dict[str, dict] = defaultdict(lambda: {"tokens_in": 0, "tokens_out": 0, "cost": 0.0, "calls": 0})

    for e in events:
        key = e.get(f"label_{dim}") or e.get(f"git_{dim}") or "(unknown)"
        g = groups[key]
        g["tokens_in"]  += e.get("input_tokens", 0)
        g["tokens_out"] += e.get("output_tokens", 0)
        g["cost"]       += e.get("cost_usd") or 0.0
        g["calls"]      += 1

    rows = sorted(groups.items(), key=lambda x: x[1]["cost"], reverse=True)
    total_in   = sum(e.get("input_tokens", 0) for e in events)
    total_out  = sum(e.get("output_tokens", 0) for e in events)
    total_cost = sum(e.get("cost_usd") or 0.0 for e in events)

    col = 36
    print(f"\nLast {args.days}d — grouped by {dim}\n")
    print(f"{'':>{col}}  {'tokens in':>12}  {'tokens out':>12}  {'cost':>10}  {'calls':>6}")
    print("─" * (col + 50))
    for key, g in rows:
        print(f"{key[:col]:>{col}}  {_fmt(g['tokens_in']):>12}  {_fmt(g['tokens_out']):>12}  ${g['cost']:>9.4f}  {g['calls']:>6}")
    print("─" * (col + 50))
    print(f"{'TOTAL':>{col}}  {_fmt(total_in):>12}  {_fmt(total_out):>12}  ${total_cost:>9.4f}  {len(events):>6}")
    print()


def _fmt(n: int) -> str:
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000:     return f"{n/1_000:.1f}k"
    return str(n)


# ── claude-code install / uninstall ───────────────────────────────────────────

def cmd_claude_code_install(args: argparse.Namespace) -> None:
    from ._claudecode import install_hooks, SETTINGS_PATH
    if install_hooks():
        print(f"✓ agentcost hook added to {SETTINGS_PATH}")
        print("  Every Claude Code session will now be tracked automatically.")
        print("  Run `agentcost report` after your next session.")
    else:
        print("Hook already installed.")


def cmd_claude_code_uninstall(args: argparse.Namespace) -> None:
    from ._claudecode import uninstall_hooks, SETTINGS_PATH
    if uninstall_hooks():
        print(f"✓ agentcost hook removed from {SETTINGS_PATH}")
    else:
        print("Hook not found in settings.")


# ── record-session (called by Claude Code Stop hook) ─────────────────────────

def cmd_record_session(args: argparse.Namespace) -> None:
    from ._claudecode import find_latest_jsonl, extract_session_usage
    from ._git import get_context as git_ctx
    from ._pricing import cost_usd
    from ._log import record, setup

    setup()
    jsonl = find_latest_jsonl()
    if not jsonl:
        return  # no sessions found, silently exit

    usage = extract_session_usage(jsonl)
    if not usage["input_tokens"] and not usage["output_tokens"]:
        return

    git = git_ctx()
    record(
        model=usage["model"],
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        cost_usd=cost_usd(usage["model"], usage["input_tokens"], usage["output_tokens"]),
        labels={"source": "claude-code"},
        git=git,
        latency_ms=None,
    )

    cost = cost_usd(usage["model"], usage["input_tokens"], usage["output_tokens"])
    pr   = git.get("pr", "")
    cost_str = f"${cost:.4f}" if cost is not None else "?"
    ctx  = f"PR #{pr}" if pr else git.get("branch", "")
    print(f"[agentcost] session: {_fmt(usage['input_tokens'])} in / {_fmt(usage['output_tokens'])} out = {cost_str}" +
          (f"  ({ctx})" if ctx else ""))


# ── proxy (local dev shortcut) ────────────────────────────────────────────────

def cmd_proxy(args: argparse.Namespace) -> None:
    try:
        import uvicorn
        from proxy.main import app
    except ImportError:
        print("Install proxy deps: pip install agentcost[proxy]")
        sys.exit(1)
    port = args.port
    print(f"[agentcost] proxy listening on :{port}")
    print(f"  ANTHROPIC_BASE_URL=http://localhost:{port}/anthropic")
    print(f"  OPENAI_BASE_URL=http://localhost:{port}/openai")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(prog="agentcost", description="Token attribution for AI agents")
    sub = parser.add_subparsers(dest="cmd")

    # report
    r = sub.add_parser("report", help="Show token spend report")
    r.add_argument("--days", type=int, default=7)
    r.add_argument("--by",   default="pr", help="pr | user | branch | team | model")

    # claude-code
    cc = sub.add_parser("claude-code", help="Claude Code integration")
    cc_sub = cc.add_subparsers(dest="cc_cmd")
    cc_sub.add_parser("install",   help="Add agentcost hook to ~/.claude/settings.json")
    cc_sub.add_parser("uninstall", help="Remove agentcost hook")

    # record-session (invoked by hook, not users directly)
    sub.add_parser("record-session")

    # proxy
    p = sub.add_parser("proxy", help="Run local attribution proxy")
    p.add_argument("--port", type=int, default=8080)

    args = parser.parse_args()

    if args.cmd == "report":
        cmd_report(args)
    elif args.cmd == "claude-code":
        if args.cc_cmd == "install":
            cmd_claude_code_install(args)
        elif args.cc_cmd == "uninstall":
            cmd_claude_code_uninstall(args)
        else:
            cc.print_help()
    elif args.cmd == "record-session":
        cmd_record_session(args)
    elif args.cmd == "proxy":
        cmd_proxy(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
