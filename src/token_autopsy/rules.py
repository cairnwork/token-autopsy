"""Derive the three money-saving rules (with estimated saving) from a summary."""
from __future__ import annotations

# Assumptions (documented in README / docs/VALIDATION.md):
#  d1: restarting/compacting at 200k removes the re-read of tokens above 200k: 50%..100% of that excess.
#  d2: replacing a sleep loop by one blocking wait removes 70%..100% of the polling calls' cost.
#  d3: trimming irrelevant tool definitions / CLAUDE.md from the base context saves 14%..16% (measured offline in r7).
#  d4: targeted search instead of ls/grep sprawl removes 30%..60% of the unfollowed browse runs.
LOW_HIGH = {
    "d1": (0.5, 1.0),
    "d2": (0.7, 1.0),
    "d3": (0.14, 0.16),
    "d4": (0.3, 0.6),
}


def derive(s: dict) -> list[dict]:
    tot = s["cost"] or 1e-9
    base_cost = s["subagents"]["base_cost"] + s["main_base"]["base_cost"]
    raw = {
        "d1": s["over200_excess_cost"],
        "d2": s["polling"]["cost"],
        "d3": base_cost,
        "d4": s["browse"]["waste_cost"],
    }
    out = []
    for code, basis in raw.items():
        lo, hi = LOW_HIGH[code]
        out.append({"code": code, "basis_cost": basis, "basis_pct": 100 * basis / tot,
                    "dedup_basis_cost": s["dedup"][code],
                    "dedup_low": s["dedup"][code] * lo, "dedup_high": s["dedup"][code] * hi,
                    "save_low": basis * lo, "save_high": basis * hi,
                    "save_low_pct": 100 * basis * lo / tot, "save_high_pct": 100 * basis * hi / tot})
    out.sort(key=lambda r: -(r["save_low"] + r["save_high"]))
    top = out[:3]
    for i, r in enumerate(top, 1):
        r["rank"] = i
    # per-rule estimates overlap (one call can match several rules); the dedup_* fields attribute
    # each call to at most one rule (priority d1 > d2 > d3 > d4) and are the only figures that may be summed.
    return top
