# token-autopsy

**English.** `token-autopsy` finds actionable usage patterns in session logs you already have. It reads your local Claude Code logs (`~/.claude/projects`) with **no model calls and no network** and points at specific, fixable patterns: very long contexts that get re-read on every call, sleep-loop polling, subagent base context, file-hunting sprawl. It is not another token dashboard (tools like cc-analyzer or token-stats already chart usage); the point is the three rules at the end. Standard library only, Python 3.10+, Claude Code only (Codex is planned for v0.2).

**中文。** `token-autopsy` 從你已有的紀錄找出可以採取行動的使用模式：只讀本機 Claude Code 紀錄（`~/.claude/projects`），**不呼叫模型、不連網**，指出超長脈絡反覆重讀、sleep 輪詢、子代理基底、找檔亂翻等可修正的模式。它不是另一套 token 儀表板，重點是最後的三條規則。只用標準庫，Python 3.10 以上，目前只支援 Claude Code（Codex 預計 v0.2）。

All dollar figures are **estimates at list price, not a bill** (subscription users pay in quota). All savings figures are **modelled estimates, not measured reductions**. The example numbers below come from **one machine's sample**, not a general rate.

## Install

```sh
git clone https://github.com/cairnwork/token-autopsy.git && cd token-autopsy
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/token-autopsy --help
```

## Usage

```sh
token-autopsy scan                         # scan ~/.claude/projects, save token-autopsy-scan.json (a few seconds: 4-6 s measured on ~600 sessions)
token-autopsy report                       # text report; add --format markdown|json, --lang zh, -o FILE
token-autopsy rules --lang zh              # the three rules with estimated saving
```

Filters (all subcommands): `--since 2026-10-01 --until 2026-10-15 --project myrepo --prices my_prices.json --jobs 4`, or a positional path to a projects directory. `report`/`rules` accept `--from token-autopsy-scan.json` to reuse a scan; `--since/--until/--project` then filter at session level (a saved scan has no per-call timestamps), and `--prices`/`--show-paths` are ignored.

Project names start with `-` and must be given as `--project=-name`.

Prices (list prices dated 2026-10-23, please keep them updated): edit `src/token_autopsy/default_prices.json` or pass `--prices FILE` (or put one at `~/.config/token-autopsy/prices.json`). Unknown models use the fallback rate and are flagged.

## Example output (one machine's sample: 3,964 files, 598 sessions, 2026-10-23; not a general rate)

```
Tokens                      27.13B
Estimated cost (secondary)  $11,905  [estimate, not a bill]

Kind           tokens   % tokens  Cost    % cost
cache re-read  26.11B   96.2%     $5,840  49.1%
cache write    977.45M  3.6%      $5,095  42.8%
Cache hits are not waste in themselves; the cost comes from how large the
context was when it was re-read.

Context  Calls   % tokens  % cost
>200k    44,032  69.6%     65.4%
Polling calls: 5194 costing $879 (7.4% of total)

1. Restart or compact once context passes 200k tokens.
   modelled estimate: 10.0-20.1% of cost; overlaps with the other rules, do not add
2. Never poll with sleep loops; use one blocking wait.
   modelled estimate: 5.2-7.4% of cost; overlaps with the other rules, do not add
3. Trim the base context (tool definitions, CLAUDE.md).
   modelled estimate: 1.3-1.5% (assumed constant); overlaps, do not add
```

The three per-rule estimates overlap and are never summed; `rules` prints one de-duplicated bound (each API call counted toward at most one rule) as the only combined figure.

See `docs/VALIDATION.md` for how these numbers compare with the earlier manual autopsy, and what each estimate assumes.

## Privacy

- Everything runs locally. **The tool opens no network connections.**
- **No raw conversation content is written**; session ids and timestamps are kept. Output (screen, JSON, Markdown, scan file) contains aggregate numbers, session ids, model names, tool-name-derived counts and timestamps.
- Project directory names are **masked as `proj-<hash>` by default** (salted hash; the random salt is created once per machine in `~/.config/token-autopsy/salt`, mode 0600, so masks cannot be reversed with a dictionary of known paths). Pass `--show-paths` to show real names.
- Prompts, file contents, command text and tool output are read in memory only to classify them (e.g. "is this a `sleep` loop?") and are never stored or printed. Repeated-command detection uses a hash that stays in memory.
- Tests use synthetic fixtures only.

## Tests

In a venv: `pip install -e .[dev]` then `pytest`.

## Limits

Claude Code only in v0.1 (Codex planned for v0.2). Savings are estimates with stated assumptions, not guarantees.

Next step: to make sure PRs merged to main are really complete and backed by evidence, see [Cairnwork](https://github.com/cairnwork/cairnwork) (the main product).

License: Apache-2.0. Author: James3014.
