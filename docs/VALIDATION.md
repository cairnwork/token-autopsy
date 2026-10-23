# Validation against the R6 autopsy

Reference: the council R6 autopsy (`knowledge/nexus/decisions/council-2026-10-22-l2-breakthrough/r6_autopsy/REPORT_ZH.md`, 3,814 files, 2026-10-08..10-22).
This run: `token-autopsy scan` on `~/.claude/projects` on 2026-10-23 (3,919 files, 582 sessions, 7.6 GB).
Speed: **3.2 s** wall clock (8 processes, warm cache; limit was 2 minutes). Only assistant lines (usage + tool_use) and the size of tool results are parsed.

| Metric | R6 | token-autopsy | Verdict |
|---|---|---|---|
| Cache re-read share of tokens | 96.4% | 96.2% | match |
| API calls / nominal cost | 120.7k / ~$50k | 128.8k / ~$55.2k | +3 days of newer logs (3,919 vs 3,814 files); same price table (Opus rates) |
| Cost at >200k context | "70% in long sessions" | per call: 68.9% of cost, 69.8% of tokens | match when measured per API call. Measured per file (any file that ever passed 200k) it is 83.3% (310 files); R6's 70% matches the per-call reading |
| Polling share | ~7.5% | 7.3% (5,374 calls: 5,187 sleep-loop, 297 repeat within 60 s) | match |
| Hours of `sleep` in commands | 119 h | 100 h | lower: we sum `sleep N[smhd]` only when it is a real command word; R6 counted looser text matches |
| Tool outputs >20k chars | 1,417 | 1,474 | match (+3 days) |
| Subagent base median | 30k | 33k | close; we use the first call's full context (input + cache) |
| Subagent base share | 47% of subagent *carry* | 16.2% of subagent *cost* (7.2% of total cost) | different definition, not comparable. R6 attributed token carry by source (counting only attributable tokens). We price the base re-read at the cache-read rate and divide by all subagent cost, which includes cache writes and output. Ordering is the same: base is the largest single carried item |
| File-hunting | ~8% | strict: 58 runs, <0.1%; loose upper bound (any call that ran ls/find/grep/cat/git log...): 58% of whole-call cost | R6's 8% is carry attribution of browse *output*. We have no per-output attribution, so the strict metric (3+ discovery commands with no read/edit after) is a lower bound and the loose one an upper bound. Neither is directly comparable |

## Method notes
- One API message is written as several lines (one per content block) with repeated usage; we de-duplicate by `message.id`.
- Context of a call = input + cache-write + cache-read tokens. Buckets: <50k, 50-200k, >200k.
- Cost uses `default_prices.json` (Opus rates for opus/fable/unknown, Sonnet, Haiku). It is a nominal list price, not a bill; subscription users pay in quota.
- Rule savings (`rules`) are estimates with explicit assumptions listed in the output; d1 (restart at 200k) is optimistic because a restart also costs a summary.
- Codex logs are not read in v0.1 (planned for v0.2).
