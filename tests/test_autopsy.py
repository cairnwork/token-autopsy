import json
import os
import subprocess
import sys

import pytest

from token_autopsy import cli
from token_autopsy.classify import classify_bash, sleep_seconds
from token_autopsy.pricing import Pricer, load_prices
from token_autopsy.report import build_blocks, build_rules_blocks, render, to_json
from token_autopsy.rules import derive
from token_autopsy.scan import mask, parse_date, scan
from token_autopsy.summarize import summarize

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "projects")


@pytest.fixture(scope="module")
def rows():
    return scan(load_prices(None), FIX, jobs=1)


@pytest.fixture(scope="module")
def summ(rows):
    return summarize(rows)


def by_id(rows, i):
    return next(r for r in rows if r["id"] == i)


def test_dedup_and_totals(rows):
    m = by_id(rows, "sess-main")
    assert m["n_calls"] == 12          # duplicate per-block lines count once
    assert m["in"] == 60 and m["out"] == 100 * 8 + 200 * 4
    assert not m["sub"] and by_id(rows, "agent-1")["sub"]
    assert all(r["id"] != "empty" for r in rows)


def test_pricing_fallback_and_cost():
    p = Pricer(load_prices(None))
    assert p.cost("claude-opus-5-5", 1_000_000, 1_000_000, 1_000_000, 1_000_000) == (15.0, 18.75, 1.5, 75.0)
    assert p.lookup("mystery-model")[1] is True
    assert p.lookup("claude-sonnet-5-5")[1] is False


def test_custom_prices(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"models": [{"match": "opus", "input": 1, "cache_write": 1, "cache_read": 1, "output": 1}]}))
    r = scan(load_prices(str(f)), FIX, jobs=1)
    assert by_id(r, "agent-1")["cost"] < 1.0


def test_context_buckets(rows, summ):
    m = by_id(rows, "sess-main")
    assert m["bucket_calls"] == [1, 7, 4]          # m1 | m2..m8 | m9..m12
    assert m["max_ctx"] == 253505
    assert summ["buckets"][2]["calls"] == 4
    assert abs(sum(b["cost_pct"] for b in summ["buckets"]) - 100) < 1e-6
    assert m["over200_excess_cost"] > 0


def test_polling(rows):
    m = by_id(rows, "sess-main")
    assert m["sleep_calls"] == 1 and m["sleep_secs"] == 30
    assert m["repeat_calls"] == 1                  # second identical command within 60 s
    assert m["poll_calls"] == 2
    assert m["poll_cost"] > 0


def test_classify_bash():
    assert classify_bash("sleep 5")[0] == "poll"
    assert classify_bash("while true; do sleep 2m; done") == ("poll", 120.0)
    assert classify_bash("ls -la && cd x")[0] == "browse"
    assert classify_bash("cat a | head")[0] == "shread"
    assert classify_bash("git log --oneline")[0] == "shread"
    assert classify_bash("python3 run.py")[0] == "other"
    assert sleep_seconds("sleep 1h") == 3600


def test_browse_waste(rows):
    m = by_id(rows, "sess-main")
    assert m["browse_calls"] == 6
    assert m["waste_runs"] == 1 and m["waste_calls"] == 3   # run before Read is not waste


def test_subagent_base(rows, summ):
    s = by_id(rows, "agent-1")
    assert s["base_ctx"] == 30005
    assert s["base_cost"] == pytest.approx(30005 * 2 * 1.5 / 1e6)
    assert summ["subagents"]["median_base_ctx"] == 30005


def test_big_outputs(rows, summ):
    assert by_id(rows, "sess-main")["big_outputs"] == 1
    assert summ["big_outputs"] == 1


def test_rollup_top_sessions(summ):
    top = summ["top_sessions"]
    assert top[0]["id"] == "sess-main" and top[0]["subagent_files"] == 1
    assert top[0]["reasons"]


def test_date_filter():
    assert scan(load_prices(None), FIX, since=parse_date("2030-01-01"), jobs=1) == []
    assert scan(load_prices(None), FIX, until=parse_date("2000-01-01", end=True), jobs=1) == []


def test_project_filter():
    assert scan(load_prices(None), FIX, project="nomatch", jobs=1) == []
    assert scan(load_prices(None), FIX, project="proj-a", jobs=1)


def test_rules(summ):
    rules = derive(summ)
    assert len(rules) == 3 and [r["rank"] for r in rules] == [1, 2, 3]
    assert all(r["save_low"] <= r["save_high"] for r in rules)


def test_paths_masked_by_default(rows):
    assert all(r["project"] == mask("-proj-a") for r in rows)
    shown = scan(load_prices(None), FIX, jobs=1, show_paths=True)
    assert all(r["project"] == "-proj-a" for r in shown)


def test_report_formats_and_privacy(summ):
    for lang in ("en", "zh"):
        txt = render(build_blocks(summ, lang), "text")
        md = render(build_blocks(summ, lang), "markdown")
        assert "sess-mai" in txt and "|" in md
        assert "-proj-a" not in txt + md          # raw project name must not leak
        assert render(build_rules_blocks(summ, lang), "text")
    assert json.loads(to_json(summ))["rules"]


def test_no_content_in_scan_rows(rows):
    blob = json.dumps(rows)
    assert "yyyy" not in blob and "grep -r foo" not in blob and "kubectl" not in blob


def test_cli_scan_and_report(tmp_path, capsys):
    out = tmp_path / "s.json"
    assert cli.main(["scan", FIX, "-o", str(out), "--jobs", "1"]) == 0
    capsys.readouterr()
    assert cli.main(["report", "--from", str(out), "--format", "json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["calls"] == 15
    assert cli.main(["rules", "--from", str(out)]) == 0


def test_cli_entry_runs():
    r = subprocess.run([sys.executable, "-m", "token_autopsy.cli", "report", FIX, "--jobs", "1"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "token-autopsy report" in r.stdout


def test_multiprocessing_matches_single(rows):
    many = scan(load_prices(None), FIX, jobs=2)
    assert sorted(r["id"] for r in many) == sorted(r["id"] for r in rows)
