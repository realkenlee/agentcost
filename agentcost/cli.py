"""agentcost CLI — `agentcost report`"""
from __future__ import annotations
import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from ._log import load_events


def cmd_report(args: argparse.Namespace) -> None:
    events = load_events()
    if not events:
        print("No events recorded yet. Add `agentcost.init()` to your code.")
        return

    # Filter by time window
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    events = [
        e for e in events
        if datetime.fromisoformat(e["ts"]) >= cutoff
    ]
    if not events:
        print(f"No events in the last {args.days} days.")
        return

    # Group by --by dimension
    dim = args.by  # e.g. "pr", "user", "team", "branch", "model"
    groups: dict[str, dict] = defaultdict(lambda: {"tokens_in": 0, "tokens_out": 0, "cost": 0.0, "calls": 0})

    for e in events:
        key = (
            e.get(f"label_{dim}")
            or e.get(f"git_{dim}")
            or "(unknown)"
        )
        g = groups[key]
        g["tokens_in"]  += e.get("input_tokens", 0)
        g["tokens_out"] += e.get("output_tokens", 0)
        g["cost"]       += e.get("cost_usd") or 0.0
        g["calls"]      += 1

    # Sort by cost descending
    rows = sorted(groups.items(), key=lambda x: x[1]["cost"], reverse=True)

    total_in   = sum(e.get("input_tokens", 0) for e in events)
    total_out  = sum(e.get("output_tokens", 0) for e in events)
    total_cost = sum(e.get("cost_usd") or 0.0 for e in events)
    total_calls = len(events)

    col = 32
    print(f"\nLast {args.days}d — grouped by {dim}\n")
    print(f"{'':>{col}}  {'tokens in':>12}  {'tokens out':>12}  {'cost':>10}  {'calls':>6}")
    print("─" * (col + 48))
    for key, g in rows:
        total_tok = g["tokens_in"] + g["tokens_out"]
        print(
            f"{key:>{col}}  "
            f"{_fmt_tok(g['tokens_in']):>12}  "
            f"{_fmt_tok(g['tokens_out']):>12}  "
            f"${g['cost']:>9.4f}  "
            f"{g['calls']:>6}"
        )
    print("─" * (col + 48))
    print(
        f"{'TOTAL':>{col}}  "
        f"{_fmt_tok(total_in):>12}  "
        f"{_fmt_tok(total_out):>12}  "
        f"${total_cost:>9.4f}  "
        f"{total_calls:>6}"
    )
    print()


def _fmt_tok(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


def main() -> None:
    parser = argparse.ArgumentParser(prog="agentcost", description="Token attribution for AI agents")
    sub = parser.add_subparsers(dest="cmd")

    r = sub.add_parser("report", help="Show token spend report")
    r.add_argument("--days", type=int, default=7, help="Look-back window in days (default: 7)")
    r.add_argument("--by",   default="pr", help="Group by: pr, user, branch, team, model (default: pr)")

    args = parser.parse_args()
    if args.cmd == "report":
        cmd_report(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
