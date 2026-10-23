# Validation against an earlier manual autopsy

Reference: a manual, one-off autopsy of the same logs (3,814 files, 2026-10-08..10-22) done with ad-hoc scripts before this tool existed. It priced everything at one flat Opus-class rate and attributed re-reads by source.
This run: `token-autopsy scan` on `~/.claude/projects` on 2026-10-23 (3,928 files, 582 sessions, 7.6 GB).
Speed: **about 3-5 seconds** wall clock (5.7 s in the last run; 8 processes; limit was 2 minutes). Only assistant lines (usage + tool_use) and the size of tool results are parsed.

| Metric | Earlier autopsy | token-autopsy | Verdict |
|---|---|---|---|
| Cache re-read share of tokens | 96.4% | 96.2% | match |
| API calls | 120.7k | 129.1k | +3 days of newer logs |
| Cost at >200k context | "70% in long sessions" | per call: 65.6% of cost, 69.8% of tokens | tokens match; the cost share is lower because the price table now uses per-model list prices (cache re-read is cheaper relative to cache writes). Per file (any file that ever passed 200k) it is 79.9% (310 files) |
| Polling share | ~7.5% | 7.6% (5,373 calls: 5,188 sleep-loop, 241 repeated within 60 s) | match |
| Hours of `sleep` in commands | 119 h | 100 h | lower: we sum `sleep N[smhd]` only when it is a real command word |
| Tool outputs >20k chars | 1,417 | 1,477 | match (+3 days) |
| Subagent base median | 30k | 33k | close; we use the first call's full context (input + cache) |
| Subagent base share | 47% of subagent *carry* | 11.8% of subagent *cost* (5.4% of total) | different definition, not comparable: the earlier number attributed token carry by source; we price the base re-read at the cache-read rate (capped by the session's real cache-read spend) and divide by all subagent cost, which includes cache writes and output |
| File-hunting | ~8% | strict: 28 runs, <0.1%; loose upper bound (any call that ran ls/find/grep/cat/git log...): 58% of whole-call cost | the earlier 8% attributed browse *output*. We have no per-output attribution, so the strict metric (browse tools spanning 3+ API calls with no read/edit after) is a lower bound and the loose one an upper bound |

## Method notes
- One API message is written as several lines (one per content block) with repeated usage; we de-duplicate by `message.id` (messages without an id are never merged).
- Context of a call = input + cache-write + cache-read tokens. Buckets: <50k, 50-200k, >200k.
- Costs use `default_prices.json`: per-model list prices dated 2026-10-23 (Opus 5.5 $4/$20, Opus 4.8/4.6 $5/$25, Fable 5.1 $10/$50, Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50 per million input/output), cache read as listed, 5-minute cache writes at 1.25x input and 1-hour writes at 2x input (read from `usage.cache_creation`). Unknown models use a flagged fallback rate. These are list prices, not a bill; subscription users pay in quota.
- A call's cost is split equally across its tool_use blocks before being attributed to polling/browsing, so parallel tools in one call are not each charged the whole call.
- Rule savings (`rules`) are estimates with explicit assumptions listed in the output. d1 (restart at 200k) is optimistic because a restart also costs a summary; the 14-16% for d3 is an assumed constant.
- Codex logs are not read in v0.1 (planned for v0.2).
