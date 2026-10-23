"""Render a summary as text, Markdown or JSON. Output holds aggregates only."""
from __future__ import annotations

import json

from .i18n import S
from .rules import derive
from .summarize import fmt_ts


def usd(x: float) -> str:
    return f"${x:,.0f}" if abs(x) >= 100 else f"${x:,.2f}"


def human(n: float) -> str:
    for unit, div in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if abs(n) >= div:
            return f"{n / div:.2f}{unit}"
    return str(int(n))


def _reason(t, code, d):
    return t["r_" + code].format(**d)


def build_blocks(s: dict, lang: str = "en") -> list:
    t = S[lang]
    B: list = [("h1", t["title"])]
    if not s["calls"]:
        return B + [("p", "No data in range.")]
    rng = f"{fmt_ts(s['range'][0])} .. {fmt_ts(s['range'][1])}" if s["range"] else "-"
    B.append(("kv", [
        (t["period"], rng),
        (t["sessions"], f"{s['sessions']} ({s['files']} {t['files']}: {s['main_files']} main + {s['sub_files']} subagent)"),
        (t["calls"], f"{s['calls']:,}"),
        (t["tokens"], human(s["total_tokens"])),
        (t["cost"], usd(s["cost"]) + "  [" + t["warn_short"] + "]"),
    ]))
    B.append(("h2", t["sec_split"]))
    tk, cp = s["tokens"], s["cost_parts"]
    rows = []
    for key, label in (("cr", "cache_read"), ("cw", "cache_write"), ("in", "new_input"), ("out", "output")):
        rows.append([t[label], human(tk[key]), f"{100 * tk[key] / s['total_tokens']:.1f}%",
                     usd(cp[key]), f"{s['cost_parts_pct'][key]:.1f}%"])
    B.append(("table", [t["kind"], "tokens", t["share_tok"], t["cost_col"], t["share_cost"]], rows))
    B.append(("p", t["warn"]))
    B.append(("p", t["cache_note"].format(tok=100 * tk["cr"] / s["total_tokens"], cost=s["cost_parts_pct"]["cr"])))
    B.append(("p", t["sample_note"]))
    B.append(("h2", t["sec_ctx"]))
    tt = s["total_tokens"] or 1
    B.append(("table", [t["bucket"], t["calls_col"], "tokens", t["share_tok"], t["cost_col"], t["share_cost"]],
              [[b["name"], f"{b['calls']:,}", human(b["tokens"]), f"{100 * b['tokens'] / tt:.1f}%",
                usd(b["cost"]), f"{b['cost_pct']:.1f}%"] for b in s["buckets"]]))
    ls = s["long_sessions"]
    B.append(("p", t["long_sessions"].format(n=ls["n"], pct=ls["cost_pct"])))
    sb, mb = s["subagents"], s["main_base"]
    B.append(("h2", t["sec_sub"]))
    B.append(("p", t["sub_line"].format(n=sb["n"], pct=sb["cost_pct"], base=sb["median_base_ctx"] // 1000)))
    B.append(("p", t["sub_base"].format(cost=usd(sb["base_cost"]), p1=sb["base_pct_of_sub"], p2=sb["base_pct_of_total"])))
    B.append(("p", t["main_base"].format(base=mb["median_base_ctx"] // 1000, p=mb["base_pct_of_main"])))
    p = s["polling"]
    B.append(("h2", t["sec_poll"]))
    B.append(("p", t["big_out"].format(n=s["big_outputs"])))
    B.append(("p", t["poll_line"].format(n=p["calls"], cost=usd(p["cost"]), pct=p["cost_pct"])))
    B.append(("p", t["poll_detail"].format(sc=p["sleep_calls"], sh=p["sleep_hours"], scost=usd(p["sleep_cost"]),
                                           rc=p["repeat_calls"], rcost=usd(p["repeat_cost"]))))
    b = s["browse"]
    B.append(("h2", t["sec_browse"]))
    B.append(("p", t["browse_line"].format(n=b["calls"], cost=usd(b["cost"]), pct=b["cost_pct"])))
    B.append(("p", t["explore_line"].format(n=b["explore_calls"], cost=usd(b["explore_cost"]), pct=b["explore_pct"])))
    B.append(("p", t["browse_waste"].format(runs=b["waste_runs"], calls=b["waste_calls"],
                                            cost=usd(b["waste_cost"]), pct=b["waste_pct"])))
    B.append(("h2", t["sec_top"]))
    rows = []
    for i, r in enumerate(s["top_sessions"], 1):
        rows.append([str(i), r["id"][:8], r["project"][-28:], usd(r["cost"]), f"{r['cost_pct']:.1f}%",
                     str(r["calls"]), "; ".join(_reason(t, c, d) for c, d in r["reasons"])])
    B.append(("table", [t["rank"], t["session"], t["project"], t["cost_col"], "%", t["calls_s"], t["why"]], rows))
    B.append(("p", t["models"] + ": " + ", ".join(f"{m} {usd(v)}" for m, v in list(s["models"].items())[:6])))
    if s["unknown_model_cost"] > 0:
        B.append(("p", t["unknown"].format(cost=usd(s["unknown_model_cost"]))))
    B.append(("p", t["privacy"]))
    B.append(("p", t["footer"]))
    return B


def build_rules_blocks(s: dict, lang: str = "en") -> list:
    t = S[lang]
    B: list = [("h1", t["rules_title"])]
    if not s["calls"]:
        return B + [("p", "No data in range.")]
    rules = derive(s)
    for r in rules:
        c = r["code"]
        why = t["why_" + c].format(basis=r["basis_pct"], n=s["polling"]["calls"],
                                   base=s["subagents"]["median_base_ctx"] // 1000)
        B.append(("h2", f"{r['rank']}. {t['rule_' + c]}"))
        B.append(("p", why))
        B.append(("p", f"{t['saving']}: {r['save_low_pct']:.1f}% - {r['save_high_pct']:.1f}% "
                       f"({usd(r['save_low'])} - {usd(r['save_high'])}); {t['modelled']}; {t['overlap_flag']}"))
    tot = s["cost"] or 1e-9
    dlo = sum(r["dedup_low"] for r in rules)
    dhi = sum(r["dedup_high"] for r in rules)
    plo, phi = 100 * dlo / tot, 100 * dhi / tot
    B.append(("p", t["dedup_bound"].format(lo=plo, hi=phi, usd_lo=usd(dlo), usd_hi=usd(dhi))))
    B.append(("p", t["overlap_note"]))
    B.append(("p", t["rules_note"]))
    B.append(("p", t["sample_note"]))
    B.append(("p", t["footer"]))
    return B


def render(blocks: list, fmt: str = "text") -> str:
    md = fmt == "markdown"
    out: list[str] = []
    for blk in blocks:
        kind = blk[0]
        if kind == "h1":
            out += [("# " if md else "") + blk[1], "" if md else "=" * len(blk[1]), ""] if not md else ["# " + blk[1], ""]
        elif kind == "h2":
            out += [("## " if md else "") + blk[1], "" if md else "-" * len(blk[1])] if not md else ["## " + blk[1], ""]
        elif kind == "p":
            out += [blk[1], ""]
        elif kind == "kv":
            w = max(len(k) for k, _ in blk[1])
            for k, v in blk[1]:
                out.append(f"- **{k}**: {v}" if md else f"{k.ljust(w)}  {v}")
            out.append("")
        elif kind == "table":
            hdr, rows = blk[1], blk[2]
            if md:
                out.append("| " + " | ".join(hdr) + " |")
                out.append("|" + "|".join("---" for _ in hdr) + "|")
                out += ["| " + " | ".join(c.replace("|", "/") for c in r) + " |" for r in rows]
            else:
                widths = [max(len(str(x)) for x in col) for col in zip(hdr, *rows)] if rows else [len(h) for h in hdr]
                last = len(hdr) - 1
                fmt_row = lambda r: "  ".join(str(c) if i == last and hdr[last] in ("Why", "原因") else str(c).ljust(widths[i])
                                              for i, c in enumerate(r))
                out.append(fmt_row(hdr))
                out.append("  ".join("-" * w for w in widths))
                out += [fmt_row(r) for r in rows]
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def to_json(s: dict) -> str:
    d = dict(s)
    d["rules"] = derive(s) if s["calls"] else []
    return json.dumps(d, indent=2, ensure_ascii=False)
