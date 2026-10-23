"""Reduce per-session rows to the aggregate numbers the report and rules use."""
from __future__ import annotations

import statistics
from datetime import datetime

SUM_KEYS = ["n_calls", "in", "cw", "cr", "out", "cost_in", "cost_cw", "cost_cr", "cost_out", "cost",
            "base_cost", "over200_excess_cost", "poll_calls", "poll_cost", "sleep_calls", "sleep_cost",
            "sleep_secs", "repeat_calls", "repeat_cost", "browse_calls", "browse_cost", "explore_calls", "explore_cost", "waste_runs",
            "waste_calls", "waste_cost", "unknown_model_cost", "big_outputs"]


def _pct(a: float, b: float) -> float:
    return 100.0 * a / b if b else 0.0


def _sum(rows, k):
    return sum(r[k] for r in rows)


def rollup(rows: list[dict]) -> list[dict]:
    """Group main + subagent rows by root session id."""
    g: dict[tuple, dict] = {}
    for r in rows:
        key = (r["tool"], r["root"])
        a = g.get(key)
        if a is None:
            a = g[key] = {k: 0 for k in SUM_KEYS}
            a.update(id=r["root"], tool=r["tool"], project=r["project"], n_files=0, n_sub=0,
                     bucket_cost=[0.0] * 3, max_ctx=0, first_ts=None, last_ts=None)
        for k in SUM_KEYS:
            a[k] += r[k]
        for i in range(3):
            a["bucket_cost"][i] += r["bucket_cost"][i]
        a["n_files"] += 1
        a["n_sub"] += 1 if r["sub"] else 0
        a["max_ctx"] = max(a["max_ctx"], r["max_ctx"])
        for k, fn in (("first_ts", min), ("last_ts", max)):
            if r[k] is not None:
                a[k] = r[k] if a[k] is None else fn(a[k], r[k])
    return list(g.values())


def reasons(a: dict) -> list[tuple[str, dict]]:
    """Tagged reasons why a session was expensive (codes + numbers only)."""
    c = a["cost"] or 1e-9
    out: list[tuple[float, str, dict]] = []
    over = _pct(a["bucket_cost"][2], c)
    if over >= 30:
        out.append((over, "long_ctx", {"pct": round(over), "max_k": a["max_ctx"] // 1000}))
    for key, code, thr in (("poll_cost", "polling", 5), ("waste_cost", "browse", 5), ("base_cost", "base", 15)):
        p = _pct(a[key], c)
        if p >= thr:
            out.append((p, code, {"pct": round(p), "n": a["poll_calls"] if code == "polling" else a["waste_runs"]}))
    p = _pct(a["cost_cw"], c)
    if p >= 35:
        out.append((p, "cache_write", {"pct": round(p)}))
    p = _pct(a["cost_out"], c)
    if p >= 15:
        out.append((p, "output", {"pct": round(p)}))
    if a["n_sub"] >= 10:
        out.append((a["n_sub"], "subagents", {"n": a["n_sub"]}))
    out.sort(key=lambda t: -t[0])
    res = [(code, d) for _, code, d in out[:3]]
    return res or [("many_calls", {"n": a["n_calls"]})]


def summarize(rows: list[dict], top: int = 10) -> dict:
    main = [r for r in rows if not r["sub"]]
    sub = [r for r in rows if r["sub"]]
    tot_cost = _sum(rows, "cost")
    tok = {k: _sum(rows, k) for k in ("in", "cw", "cr", "out")}
    all_tok = sum(tok.values())
    buckets = []
    for i, name in enumerate(("<50k", "50-200k", ">200k")):
        bc = sum(r["bucket_cost"][i] for r in rows)
        buckets.append({"name": name, "cost": bc, "cost_pct": _pct(bc, tot_cost),
                        "calls": sum(r["bucket_calls"][i] for r in rows),
                        "tokens": sum(r["bucket_tok"][i] for r in rows)})
    long_rows = [r for r in rows if r["max_ctx"] > 200_000]
    sub_cost = _sum(sub, "cost")
    sub_base = _sum(sub, "base_cost")
    base_ctxs = [r["base_ctx"] for r in sub if r["n_calls"] > 1]
    main_base_ctxs = [r["base_ctx"] for r in main if r["n_calls"] > 1]
    models: dict[str, float] = {}
    for r in rows:
        for m, v in r["models"].items():
            models[m] = models.get(m, 0.0) + v
    roots = rollup(rows)
    roots.sort(key=lambda a: -a["cost"])
    top_rows = []
    for a in roots[:top]:
        top_rows.append({
            "id": a["id"], "tool": a["tool"], "project": a["project"], "cost": a["cost"],
            "cost_pct": _pct(a["cost"], tot_cost), "calls": a["n_calls"], "subagent_files": a["n_sub"],
            "max_ctx": a["max_ctx"], "over200_pct": _pct(a["bucket_cost"][2], a["cost"]),
            "first_ts": a["first_ts"], "reasons": reasons(a)})
    tss = [r["first_ts"] for r in rows if r["first_ts"]] + [r["last_ts"] for r in rows if r["last_ts"]]
    return {
        "sessions": len(roots), "files": len(rows), "main_files": len(main), "sub_files": len(sub),
        "tools": {t: sum(1 for r in rows if r["tool"] == t) for t in sorted({r["tool"] for r in rows})},
        "range": [min(tss), max(tss)] if tss else None,
        "calls": _sum(rows, "n_calls"), "tokens": tok, "total_tokens": all_tok,
        "cache_read_pct": _pct(tok["cr"], all_tok),
        "cost": tot_cost,
        "cost_parts": {k: _sum(rows, "cost_" + k) for k in ("in", "cw", "cr", "out")},
        "cost_parts_pct": {k: _pct(_sum(rows, "cost_" + k), tot_cost) for k in ("in", "cw", "cr", "out")},
        "main_cost": _sum(main, "cost"), "sub_cost": sub_cost,
        "buckets": buckets,
        "long_sessions": {"n": len(long_rows), "cost": _sum(long_rows, "cost"),
                          "cost_pct": _pct(_sum(long_rows, "cost"), tot_cost)},
        "over200_excess_cost": _sum(rows, "over200_excess_cost"),
        "subagents": {
            "n": len(sub), "cost": sub_cost, "cost_pct": _pct(sub_cost, tot_cost),
            "median_base_ctx": int(statistics.median(base_ctxs)) if base_ctxs else 0,
            "base_cost": sub_base, "base_pct_of_sub": _pct(sub_base, sub_cost),
            "base_pct_of_total": _pct(sub_base, tot_cost)},
        "main_base": {"median_base_ctx": int(statistics.median(main_base_ctxs)) if main_base_ctxs else 0,
                      "base_cost": _sum(main, "base_cost"),
                      "base_pct_of_main": _pct(_sum(main, "base_cost"), _sum(main, "cost"))},
        "big_outputs": _sum(rows, "big_outputs"),
        "polling": {
            "calls": _sum(rows, "poll_calls"), "cost": _sum(rows, "poll_cost"),
            "cost_pct": _pct(_sum(rows, "poll_cost"), tot_cost),
            "sleep_calls": _sum(rows, "sleep_calls"), "sleep_cost": _sum(rows, "sleep_cost"),
            "sleep_hours": _sum(rows, "sleep_secs") / 3600.0,
            "repeat_calls": _sum(rows, "repeat_calls"), "repeat_cost": _sum(rows, "repeat_cost")},
        "browse": {
            "calls": _sum(rows, "browse_calls"), "cost": _sum(rows, "browse_cost"),
            "cost_pct": _pct(_sum(rows, "browse_cost"), tot_cost),
            "explore_calls": _sum(rows, "explore_calls"), "explore_cost": _sum(rows, "explore_cost"),
            "explore_pct": _pct(_sum(rows, "explore_cost"), tot_cost),
            "waste_runs": _sum(rows, "waste_runs"), "waste_calls": _sum(rows, "waste_calls"),
            "waste_cost": _sum(rows, "waste_cost"), "waste_pct": _pct(_sum(rows, "waste_cost"), tot_cost)},
        "models": dict(sorted(models.items(), key=lambda kv: -kv[1])),
        "unknown_model_cost": _sum(rows, "unknown_model_cost"),
        "top_sessions": top_rows,
    }


def fmt_ts(ts) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "-"
