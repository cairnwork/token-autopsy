"""token-autopsy command line: scan | report | rules."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import __version__
from .pricing import load_prices
from .report import build_blocks, build_rules_blocks, render, to_json
from .scan import CLAUDE_ROOT, get_salt, mask, parse_date, scan
from .summarize import summarize

DEFAULT_SCAN_FILE = "token-autopsy-scan.json"


def add_source_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("path", nargs="?", help="Claude Code projects dir (default ~/.claude/projects)")
    p.add_argument("--since", metavar="YYYY-MM-DD", help="only API calls on/after this date (local time)")
    p.add_argument("--until", metavar="YYYY-MM-DD", help="only API calls up to and including this date")
    p.add_argument("--project", help="only projects whose directory name contains this text")
    p.add_argument("--prices", help="price table JSON (default: ~/.config/token-autopsy/prices.json or built-in)")
    p.add_argument("--jobs", type=int, help="worker processes (default: min(8, cpus))")
    p.add_argument("--show-paths", action="store_true",
                   help="show real project directory names (default: masked as proj-<hash>)")
    p.add_argument("--from", dest="from_file", metavar="SCAN.json", help="use a saved scan instead of scanning again")


def add_output_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--lang", choices=("en", "zh"), default="en", help="output language (default en)")
    p.add_argument("--top", type=int, default=10, help="number of top sessions (default 10)")


def filter_rows(rows: list[dict], since: str | None, until: str | None, project: str | None) -> list[dict]:
    """Session-level filter for saved scans: a row is kept if its time span overlaps the range
    (a saved scan has no per-call timestamps) and its project matches: substring of the stored name
    (scans made with --show-paths) or exact name whose salted mask equals the stored mask."""
    lo = parse_date(since) if since else None
    hi = parse_date(until, end=True) if until else None
    out = []
    for r in rows:
        if lo is not None and (r["last_ts"] is None or r["last_ts"] < lo):
            continue
        if hi is not None and (r["first_ts"] is None or r["first_ts"] >= hi):
            continue
        if project and project not in r["project"] and mask(project, get_salt()) != r["project"]:
            continue
        out.append(r)
    return out


SCAN_ERRORS: list = []


def run_scan(a) -> list[dict]:
    if a.from_file:
        with open(a.from_file, encoding="utf-8") as f:
            rows = json.load(f)["sessions"]
        if a.prices or getattr(a, "show_paths", False):
            print("note: --prices and --show-paths are ignored with --from (re-run scan to change them)",
                  file=sys.stderr)
        return filter_rows(rows, a.since, a.until, a.project)
    table = load_prices(a.prices)
    claude = a.path or CLAUDE_ROOT
    since = parse_date(a.since) if a.since else None
    until = parse_date(a.until, end=True) if a.until else None
    SCAN_ERRORS.clear()
    return scan(table, claude, since, until, a.project, a.jobs, getattr(a, "show_paths", False),
                errors=SCAN_ERRORS)


def report_errors(a) -> int:
    """List unreadable files on stderr (project dir masked unless --show-paths); return exit code."""
    if not SCAN_ERRORS:
        return 0
    salt = "" if getattr(a, "show_paths", False) else get_salt()
    print(f"error: {len(SCAN_ERRORS)} file(s) could not be read; totals are UNDERESTIMATED:", file=sys.stderr)
    root = os.path.expanduser(getattr(a, "path", None) or CLAUDE_ROOT)
    for e in SCAN_ERRORS[:20]:
        rel = os.path.relpath(e["path"], root).split(os.sep)
        if salt:
            rel[0] = mask(rel[0], salt)
        print(f"  {e['error']}: {os.sep.join(rel)}", file=sys.stderr)
    if len(SCAN_ERRORS) > 20:
        print(f"  ... and {len(SCAN_ERRORS) - 20} more", file=sys.stderr)
    return 3


def cmd_scan(a) -> int:
    t0 = time.time()
    rows = run_scan(a)
    out = a.output or DEFAULT_SCAN_FILE
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "tool": "token-autopsy " + __version__, "sessions": rows}, f)
    s = summarize(rows)
    print(f"scanned {s['files']} files / {s['sessions']} sessions / {s['calls']:,} calls "
          f"in {time.time() - t0:.1f}s; estimated cost ${s['cost']:,.0f}; saved {out}")
    return report_errors(a)


def cmd_report(a) -> int:
    s = summarize(run_scan(a), a.top)
    if a.format == "json":
        text = to_json(s) + "\n"
    else:
        text = render(build_blocks(s, a.lang), a.format)
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return report_errors(a)


def cmd_rules(a) -> int:
    s = summarize(run_scan(a), a.top)
    if a.format == "json":
        d = json.loads(to_json(s))
        sys.stdout.write(json.dumps(d["rules"], indent=2) + "\n")
    else:
        sys.stdout.write(render(build_rules_blocks(s, a.lang), a.format))
    return report_errors(a)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="token-autopsy", description="Where did my tokens go? Zero-model cost autopsy of local session logs.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("scan", help="scan logs and save aggregate numbers to a JSON file")
    add_source_args(p)
    p.add_argument("-o", "--output", help=f"scan file to write (default ./{DEFAULT_SCAN_FILE})")
    p.set_defaults(fn=cmd_scan)
    p = sub.add_parser("report", help="print the cost autopsy report")
    add_source_args(p); add_output_args(p)
    p.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    p.add_argument("-o", "--output", help="write to this file instead of stdout")
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("rules", help="print the three rules with estimated saving")
    add_source_args(p); add_output_args(p)
    p.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    p.set_defaults(fn=cmd_rules)
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("scan", "report", "rules", "-h", "--help", "--version"):
        argv = ["scan"] + argv        # bare `token-autopsy [options]` means `scan`
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
