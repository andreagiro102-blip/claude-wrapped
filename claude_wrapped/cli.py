"""Command line entry point: `claude-wrapped`."""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from datetime import date

from . import __version__
from .pricing import load_prices
from .render import render
from .scan import default_claude_dir, retention_days, scan
from .stats import NoData, build


def _date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {s!r}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="claude-wrapped",
                                 description="Your Claude Code year (or month) in review, from local logs.")
    ap.add_argument("--year", type=int, help="only this calendar year")
    ap.add_argument("--since", type=_date, help="start date, YYYY-MM-DD")
    ap.add_argument("--until", type=_date, help="end date, YYYY-MM-DD")
    ap.add_argument("-o", "--out", default="claude-wrapped.html", help="output HTML file")
    ap.add_argument("--json", action="store_true", help="print the numbers as JSON instead of writing HTML")
    ap.add_argument("--hide-projects", action="store_true", help="replace project names with 'Project 1, 2...'")
    ap.add_argument("--prices", help="JSON file with extra/override model prices")
    ap.add_argument("--claude-dir", default=default_claude_dir(), help="Claude Code config dir (default ~/.claude)")
    ap.add_argument("--no-open", action="store_true", help="do not open the report in the browser")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    a = ap.parse_args(argv)

    since, until = a.since, a.until
    if a.year:
        since, until = since or date(a.year, 1, 1), until or date(a.year, 12, 31)

    if not os.path.isdir(os.path.join(a.claude_dir, "projects")):
        print(f"No Claude Code logs found in {a.claude_dir}/projects", file=sys.stderr)
        return 1

    sc = scan(a.claude_dir)
    try:
        s = build(sc, load_prices(a.prices), since, until, a.hide_projects)
    except NoData as e:
        print(e, file=sys.stderr)
        return 1

    if a.json:
        print(json.dumps(s, default=str, indent=2))
        return 0

    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(render(s))
    path = os.path.abspath(a.out)
    print(f"Read {sc.files} log files, {s['messages']:,} assistant messages "
          f"({s['period']['start']} to {s['period']['end']}).")   # ASCII only: Windows consoles are cp1252
    print(f"Report: {path}")

    keep = retention_days(a.claude_dir)
    if keep is None or keep <= 30:
        print("\nNote: Claude Code deletes transcripts older than "
              f"{keep or 30} days, so older history is missing. To keep more next time, add\n"
              '  "cleanupPeriodDays": 365\n'
              f"to {os.path.join(a.claude_dir, 'settings.json')}")
    if s["unpriced"]:
        print(f"\nNo price for: {', '.join(sorted(s['unpriced']))} (tokens counted, cost not). See --prices.")

    if not a.no_open:
        webbrowser.open(f"file://{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
