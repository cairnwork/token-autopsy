# Validation against an earlier manual autopsy

Reference: a manual, one-off autopsy of the same logs (3,814 files, 2026-10-08..10-22) done with ad-hoc scripts before this tool existed. It priced everything at one flat Opus-class rate and attributed re-reads by source.
This run: `token-autopsy scan` on `~/.claude/projects` on 2026-10-23 (3,995 files, 618 sessions, 7.6 GB).
Speed: **a few seconds** wall clock (4-7 s measured on ~600 sessions; 8 processes; limit was 2 minutes). Only assistant lines (usage + tool_use) and the size of tool results are parsed.

| Metric | Earlier autopsy | token-autopsy | Verdict |
|---|---|---|---|
| Cache re-read share of tokens | 96.4% | 96.2% | match |
| API calls | 120.7k | 131.3k | +3 days of newer logs |
| Cost at >200k context | "70% in long sessions" | per call: 65.3% of cost, 69.6% of tokens | tokens match; the cost share is lower because the price table now uses per-model list prices (cache re-read is cheaper relative to cache writes). Per file (any file that ever passed 200k) it is 79.8% (318 files) |
| Polling share | ~7.5% | 7.3% (5,203 calls: 5,016 sleep-loop, 243 repeated within 60 s) | match |
| Hours of `sleep` in commands | 119 h | 92 h | lower: `sleep` counts only when it is the first word of a (sub-)command, so `echo "sleep 5"` or `grep sleep` do not count |
| Tool outputs >20k chars | 1,417 | 1,803 | higher: +3 days of logs, and the pre-filter no longer assumes a fixed field order (an earlier version missed some results) |
| Subagent base median | 30k | 34k | close; we use the first call's full context (input + cache) |
| Subagent base share | 47% of subagent *carry* | 11.5% of subagent *cost* (5.3% of total) | different definition, not comparable: the earlier number attributed token carry by source; we price the base re-read at the cache-read rate (capped by the session's real cache-read spend) and divide by all subagent cost, which includes cache writes and output |
| File-hunting | ~8% | strict: 28 runs, <0.1%; loose upper bound (any call that ran ls/find/grep/cat/git log...): 57% of whole-call cost | the earlier 8% attributed browse *output*. We have no per-output attribution, so the strict metric (browse tools spanning 3+ API calls with no read/edit after) is a lower bound and the loose one an upper bound |

## Method notes
- One API message is written as several lines (one per content block) with repeated usage; we de-duplicate by `message.id` (messages without an id are never merged).
- Context of a call = input + cache-write + cache-read tokens. Buckets: <50k, 50-200k, >200k.
- Costs use `default_prices.json`: per-model list prices dated 2026-10-23 (Opus 5.5 $4/$20, Opus 4.8/4.6 $5/$25, Fable 5.1 $10/$50, Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50 per million input/output), cache read as listed, 5-minute cache writes at 1.25x input and 1-hour writes at 2x input (read from `usage.cache_creation`). Unknown models use a flagged fallback rate. These are list prices, not a bill; subscription users pay in quota.
- A call's cost is split equally across its tool_use blocks before being attributed to polling/browsing, so parallel tools in one call are not each charged the whole call.
- Rule savings (`rules`) are estimates with explicit assumptions listed in the output. d1 (restart at 200k) is optimistic because a restart also costs a summary; the 14-16% for d3 is an assumed constant.
- Codex logs are not read in v0.1 (planned for v0.2).

## Savings estimates (post-review)
- Per-rule savings are **modelled estimates, not measured reductions**, and the rules overlap (one call can be long-context, polling and base re-read at once), so they are never summed.
- `rules` prints one de-duplicated bound: every API call is attributed to at most one rule (priority d1 > d2 > d3 > d4) and only that part is counted. On the 2026-10-23 sample the bound is 11.9%-22.6% of estimated cost, against 16.7%-29.3% for the old plain sum.
- All figures come from one machine's sample, not a general rate; API list-price equivalents do not translate directly into subscription quota.
- Cache re-read is 96.2% of tokens but 49.0% of cost; cache hits are not waste in themselves.

## Tool-call counting check
Claude Code writes one streamed message as several lines. We verified on a random sample of 300 real session files (24,506 tool_use blocks) that no tool_use id appears on more than one line, so tool counts were not inflated. The parser still de-duplicates by tool_use id (and by message id for usage) as a safeguard, and has a test for it.

## Correctness fixes from the Codex review (Issue #2)
- Base re-read cost is summed per call at each call's own model price (a session that switches Opus -> Haiku no longer bills the whole base at the first model's price).
- Files that cannot be read (e.g. PermissionError) are counted, listed on stderr (project directory masked unless `--show-paths`) and make the command exit with code 3; totals are then flagged as underestimated instead of silently skipping the file.
- Oversized tool outputs are filtered by their own timestamp under `--since/--until`.
- A bare-date `--until` adds one calendar day, not 86,400 s, so DST days (23 h or 25 h) are handled; tested in `America/Los_Angeles`.
