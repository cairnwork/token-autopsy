"""Scan session logs and reduce each session to a row of aggregate numbers.

Privacy: rows contain only counts, token numbers, costs, timestamps, model names,
session ids and project directory names. No prompt, tool input or output text is
ever stored.
"""
from __future__ import annotations

import glob
import json
import multiprocessing as mp
import os
import statistics
from datetime import datetime, timezone

import hashlib

from .classify import classify_tool
from .pricing import Pricer

BUCKETS = (50_000, 200_000)  # <50k, 50-200k, >200k
CLAUDE_ROOT = "~/.claude/projects"
BIG_OUTPUT_CHARS = 20_000
REPEAT_WINDOW = 60.0
MIN_BROWSE_RUN = 3


def parse_ts(s) -> float | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def bucket_of(ctx: int) -> int:
    return 0 if ctx < BUCKETS[0] else (1 if ctx <= BUCKETS[1] else 2)


# ---------------------------------------------------------------- parsers
def _big_results(line: str) -> int:
    """Count tool_result blocks larger than BIG_OUTPUT_CHARS (sizes only, text discarded)."""
    try:
        o = json.loads(line)
    except ValueError:
        return 0
    c = (o.get("message") or {}).get("content")
    n = 0
    if isinstance(c, list):
        for b in c:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                x = b.get("content")
                size = len(x) if isinstance(x, str) else sum(len(y.get("text") or "") for y in x if isinstance(y, dict)) if isinstance(x, list) else 0
                if size > BIG_OUTPUT_CHARS:
                    n += 1
    return n


def config_dir() -> str:
    return os.environ.get("TOKEN_AUTOPSY_HOME") or os.path.expanduser("~/.config/token-autopsy")


def get_salt() -> str:
    """Per-machine random salt for path masking, created on first use (mode 0600)."""
    path = os.path.join(config_dir(), "salt")
    try:
        with open(path, encoding="ascii") as f:
            salt = f.read().strip()
        if salt:
            return salt
    except OSError:
        pass
    salt = os.urandom(16).hex()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(salt)
    except OSError:
        pass  # unwritable config dir: salt is per-run (masks stay unlinkable, just not stable)
    return salt


def mask(name: str, salt: str = "") -> str:
    return "proj-" + hashlib.sha256((salt + "\0" + name).encode()).hexdigest()[:8]


def parse_claude(path: str):
    """Yield-free parser: returns (calls, tools). Calls are dicts, tools are tuples."""
    calls, tools, idx = [], [], {}
    big = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"type":"assistant"' not in line:
                if '"tool_result"' in line and len(line) > BIG_OUTPUT_CHARS and '"type":"user"' in line[:200]:
                    big += _big_results(line)
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("type") != "assistant":
                continue
            m = o.get("message") or {}
            u = m.get("usage")
            model = m.get("model") or ""
            if not isinstance(u, dict) or model == "<synthetic>":
                continue
            mid = m.get("id")
            ts = parse_ts(o.get("timestamp"))
            ci = idx.get(mid) if mid else None
            out = u.get("output_tokens") or 0
            if ci is None:
                ci = len(calls)
                if mid:
                    idx[mid] = ci
                cc = u.get("cache_creation")
                cw1h = (cc.get("ephemeral_1h_input_tokens") or 0) if isinstance(cc, dict) else 0
                calls.append({"cw1h": cw1h,
                    "ts": ts, "model": model, "in": u.get("input_tokens") or 0,
                    "cw": u.get("cache_creation_input_tokens") or 0,
                    "cr": u.get("cache_read_input_tokens") or 0, "out": out})
            elif out > calls[ci]["out"]:
                calls[ci]["out"] = out
            content = m.get("content")
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        kind, key, secs = classify_tool(b.get("name") or "", b.get("input"))
                        tools.append((ci, ts, kind, key, secs))
    return calls, tools, big


# --------------------------------------------------------------- analysis
def _zero_row(sid, root, project, tool, sub):
    return {
        "id": sid, "root": root, "project": project, "tool": tool, "sub": sub,
        "models": {}, "n_calls": 0, "in": 0, "cw": 0, "cr": 0, "out": 0,
        "cost_in": 0.0, "cost_cw": 0.0, "cost_cr": 0.0, "cost_out": 0.0, "cost": 0.0,
        "bucket_cost": [0.0] * 3, "bucket_tok": [0] * 3, "bucket_calls": [0] * 3,
        "max_ctx": 0, "median_ctx": 0, "base_ctx": 0, "base_cost": 0.0,
        "over200_excess_cost": 0.0, "dd_d1": 0.0, "dd_d2": 0.0, "dd_d3": 0.0, "dd_d4": 0.0,
        "poll_calls": 0, "poll_cost": 0.0, "sleep_calls": 0, "sleep_cost": 0.0, "sleep_secs": 0.0,
        "repeat_calls": 0, "repeat_cost": 0.0,
        "browse_calls": 0, "browse_cost": 0.0, "explore_calls": 0, "explore_cost": 0.0, "waste_runs": 0, "waste_calls": 0, "waste_cost": 0.0,
        "unknown_model_cost": 0.0, "big_outputs": 0, "first_ts": None, "last_ts": None,
    }


def analyze(calls, tools, pricer: Pricer, row: dict, since=None, until=None) -> dict | None:
    """Fill `row` from parsed calls/tools. Returns None if nothing in range."""
    if since is not None or until is not None:
        keep = {}
        new_calls = []
        for i, c in enumerate(calls):
            ts = c["ts"]
            if ts is None or (since is not None and ts < since) or (until is not None and ts >= until):
                continue
            keep[i] = len(new_calls)
            new_calls.append(c)
        tools = [(keep[t[0]],) + t[1:] for t in tools if t[0] in keep]
        calls = new_calls
    if not calls:
        return None
    n = len(calls)
    costs = [0.0] * n
    ctxs = [0] * n
    excess: dict[int, float] = {}
    basecost: dict[int, float] = {}
    ctxs0 = calls[0]["in"] + calls[0]["cw"] + calls[0]["cr"]
    for i, c in enumerate(calls):
        ci, cw, cr, co = pricer.cost(c["model"], c["in"], c["cw"], c["cr"], c["out"], c.get("cw1h", 0))
        tot = ci + cw + cr + co
        ctx = c["in"] + c["cw"] + c["cr"]
        costs[i], ctxs[i] = tot, ctx
        b = bucket_of(ctx)
        p, fb = pricer.lookup(c["model"])
        row["in"] += c["in"]; row["cw"] += c["cw"]; row["cr"] += c["cr"]; row["out"] += c["out"]
        row["cost_in"] += ci; row["cost_cw"] += cw; row["cost_cr"] += cr; row["cost_out"] += co
        row["cost"] += tot
        row["bucket_cost"][b] += tot
        row["bucket_tok"][b] += ctx + c["out"]
        row["bucket_calls"][b] += 1
        row["models"][c["model"]] = row["models"].get(c["model"], 0.0) + tot
        if fb:
            row["unknown_model_cost"] += tot
        if ctx > BUCKETS[1]:
            e = (ctx - BUCKETS[1]) * p["cache_read"] / 1e6
            row["over200_excess_cost"] += e
            excess[i] = e
        if i > 0:
            basecost[i] = min(ctxs0, c["cr"]) * p["cache_read"] / 1e6
    row["n_calls"] = n
    row["max_ctx"] = max(ctxs)
    row["median_ctx"] = int(statistics.median(ctxs))
    first = calls[0]
    row["base_ctx"] = ctxs[0]
    p0, _ = pricer.lookup(first["model"])
    row["base_cost"] = min(ctxs[0] * (n - 1) * p0["cache_read"] / 1e6, row["cost_cr"])
    tss = [c["ts"] for c in calls if c["ts"] is not None]
    row["first_ts"], row["last_ts"] = (min(tss), max(tss)) if tss else (None, None)

    # Per-tool attribution: a call's cost is split equally among its tool_use blocks, so a call
    # that runs one flagged tool among three is charged one third, not the whole call.
    ntools: dict[int, int] = {}
    for t in tools:
        ntools[t[0]] = ntools.get(t[0], 0) + 1

    def share(counts: dict[int, int]) -> float:
        return sum(costs[i] * k / ntools[i] for i, k in counts.items())

    def bump(d, ci):
        d[ci] = d.get(ci, 0) + 1

    sleep_t, repeat_t, poll_t, browse_t, explore_t = {}, {}, {}, {}, {}
    last_seen: dict[str, tuple[float, int]] = {}
    for (ci, ts, kind, key, secs) in tools:
        flagged_poll = kind == "poll"
        if flagged_poll:
            bump(sleep_t, ci)
            row["sleep_secs"] += secs
        rep_hit = False
        if key is not None and ts is not None:
            prev = last_seen.get(key)
            if prev is not None and prev[1] != ci and 0 <= ts - prev[0] <= REPEAT_WINDOW:
                rep_hit = True
                bump(repeat_t, ci)
            last_seen[key] = (ts, ci)
        if flagged_poll or rep_hit:
            bump(poll_t, ci)
        if kind == "browse":
            bump(browse_t, ci)
        if kind in ("browse", "shread"):
            bump(explore_t, ci)
    row["sleep_calls"], row["sleep_cost"] = len(sleep_t), share(sleep_t)
    row["repeat_calls"], row["repeat_cost"] = len(repeat_t), share(repeat_t)
    row["poll_calls"], row["poll_cost"] = len(poll_t), share(poll_t)
    row["browse_calls"], row["browse_cost"] = len(browse_t), share(browse_t)
    row["explore_calls"], row["explore_cost"] = len(explore_t), share(explore_t)

    # file-hunting: browse tools spanning >=3 distinct API calls, not followed by a read/edit
    run: list[int] = []
    waste_t: dict[int, int] = {}
    runs = 0

    def close_run(next_kind):
        nonlocal runs
        if len(set(run)) >= MIN_BROWSE_RUN and next_kind not in ("read", "shread", "edit"):
            runs += 1
            for c_ in run:
                bump(waste_t, c_)

    for (ci, ts, kind, key, secs) in tools:
        if kind == "browse":
            run.append(ci)
        else:
            close_run(kind)
            run = []
    close_run(None)
    row["waste_runs"], row["waste_calls"] = runs, len(waste_t)
    row["waste_cost"] = share(waste_t)

    # De-duplicated attribution: each call counts toward at most one rule, priority d1 > d2 > d3 > d4.
    for i in range(n):
        w = costs[i] * waste_t[i] / ntools[i] if i in waste_t else 0.0
        pl = costs[i] * poll_t[i] / ntools[i] if i in poll_t else 0.0
        if excess.get(i):
            row["dd_d1"] += excess[i]
        elif pl:
            row["dd_d2"] += pl
        elif basecost.get(i):
            row["dd_d3"] += basecost[i]
        elif w:
            row["dd_d4"] += w
    return row


# ----------------------------------------------------------------- driver
def discover(claude_root: str, project: str | None):
    root = os.path.expanduser(claude_root)
    files = []
    for p in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
        rel = os.path.relpath(p, root)
        if project and project not in rel.split(os.sep)[0]:
            continue
        files.append(p)
    return files


_G: dict = {}


def _init(table, since, until, claude_root, show_paths, salt=""):
    _G.update(pricer=Pricer(table), since=since, until=until,
              claude_root=os.path.expanduser(claude_root), show_paths=show_paths, salt=salt)


def _work(path):
    try:
        parts = os.path.relpath(path, _G["claude_root"]).split(os.sep)
        project = parts[0] if _G["show_paths"] else mask(parts[0], _G["salt"])
        stem = os.path.splitext(parts[-1])[0]
        sub = "subagents" in parts
        root = parts[1] if sub and len(parts) >= 4 and parts[1] != "subagents" else stem
        calls, tools, big = parse_claude(path)
        if not calls:
            return None
        row = _zero_row(stem, root, project, "claude", sub)
        row["big_outputs"] = big
        return analyze(calls, tools, _G["pricer"], row, _G["since"], _G["until"])
    except OSError:
        return None


def scan(table: dict, claude_root: str = CLAUDE_ROOT, since: float | None = None, until: float | None = None,
         project: str | None = None, jobs: int | None = None, show_paths: bool = False) -> list[dict]:
    files = discover(claude_root, project)
    files.sort(key=lambda p: -os.path.getsize(p))  # big first for load balance
    jobs = jobs or min(8, os.cpu_count() or 1)
    args = (table, since, until, claude_root, show_paths, "" if show_paths else get_salt())
    if jobs <= 1 or len(files) < 2:
        _init(*args)
        return [r for r in map(_work, files) if r]
    with mp.Pool(jobs, initializer=_init, initargs=args) as pool:
        return [r for r in pool.imap_unordered(_work, files, chunksize=4) if r]


def parse_date(s: str, end: bool = False) -> float:
    """YYYY-MM-DD (local midnight; end=True gives the next midnight) or ISO datetime."""
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
        ts = d.timestamp()
        return ts + 86400 if end else ts
    except ValueError:
        return datetime.fromisoformat(s).replace(tzinfo=None).timestamp() if "+" not in s and "Z" not in s \
            else datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
