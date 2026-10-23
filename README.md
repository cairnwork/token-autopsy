# token-autopsy

**English.** Where did my tokens go? `token-autopsy` reads your local Claude Code session logs (`~/.claude/projects`) with **no model calls and no network**, and tells you how much of your usage is cache re-reads, how much was spent at huge context sizes, how much goes to polling loops and subagent base context, and which three rules would save the most. Think of it as a way to hit your weekly plan limit less often. Standard library only, Python 3.10+.

**中文。** 「我的 token 花到哪去了？」`token-autopsy` 只讀本機 Claude Code 的 session 紀錄（`~/.claude/projects`），**不呼叫任何模型、不連網**，列出快取重讀比例、超長脈絡（>200k）的花費、輪詢與子代理基底浪費，並給出最能省額度的三條規則（照改可少撞幾次每週上限）。只用標準庫，Python 3.10 以上。

All dollar figures are **estimates at nominal list price, not a bill** (subscription users pay in quota). The primary measures are token counts and usage share.

## Install

```sh
git clone <this repo> && cd token-autopsy
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/token-autopsy --help
```

## Usage

```sh
token-autopsy scan                         # scan ~/.claude/projects, save token-autopsy-scan.json (~seconds)
token-autopsy report                       # text report; add --format markdown|json, --lang zh, -o FILE
token-autopsy rules --lang zh              # the three rules with estimated saving
```

Filters (all subcommands): `--since 2026-10-01 --until 2026-10-15 --project myrepo --prices my_prices.json --jobs 4`, or a positional path to a projects directory. `report`/`rules` accept `--from token-autopsy-scan.json` to reuse a scan.

Prices: edit `src/token_autopsy/default_prices.json` or pass `--prices FILE` (or put one at `~/.config/token-autopsy/prices.json`). Unknown models use the fallback rate and are flagged.

## Example output (numbers from the author's machine, 3,919 files)

```
Tokens                      26.81B
Estimated cost (secondary)  $55,227  [estimate, not a bill]

Kind           tokens   % tokens  Cost     % cost
cache re-read  25.80B   96.2%     $36,536  66.2%
cache write    969.00M  3.6%      $15,993  29.0%
Context  Calls   tokens   % tokens  Cost     % cost
<50k     16,618  464.10M  1.7%      $1,914   3.5%
50-200k  68,607  7.63B    28.5%     $15,258  27.6%
>200k    43,503  18.72B   69.8%     $38,055  68.9%
Polling calls: 5373 costing $4,046 (7.3% of total)

1. Restart or compact once context passes 200k tokens.  saves 13.5% - 27.0%
2. Never poll with sleep loops; use one blocking wait.   saves 5.1% - 7.3%
3. Trim the base context (tool definitions, CLAUDE.md).   saves 1.9% - 2.1%
```

See `docs/VALIDATION.md` for how these numbers compare with the earlier manual autopsy, and what each estimate assumes.

## Privacy

- Everything runs locally. **The tool opens no network connections.**
- Output (screen, JSON, Markdown, scan file) contains only aggregate numbers, session ids, model names, tool-name-derived counts and timestamps.
- Project directory names are **masked as `proj-<hash>` by default**; pass `--show-paths` to show them.
- Prompts, file contents, command text and tool output are read in memory only to classify them (e.g. "is this a `sleep` loop?") and are never stored or printed. Repeated-command detection uses a hash that stays in memory.
- Tests use synthetic fixtures only.

## Tests

In a venv: `pip install -e .[dev]` then `pytest`.

## Limits

Claude Code only in v0.1 (Codex planned for v0.2). Savings are estimates with stated assumptions, not guarantees.

Next step: to make sure PRs merged to main are really complete and backed by evidence, see [Cairnwork](https://github.com/cairnwork/cairnwork) (the main product).

License: Apache-2.0. Author: James3014.
