# Changelog

## 0.1.0 (Codex review, Issue #2)
- Base re-read cost uses each call's own model price.
- Unreadable files are reported and give exit code 3 instead of being silently skipped.
- Large tool outputs are filtered by timestamp with `--since/--until`.
- Bare-date `--until` adds a calendar day (DST-safe).

## 0.1.0 (second external review, Issue #1)
- tool_use blocks de-duplicated by block id (verified no inflation on real logs: 0 duplicates in 24,506 blocks).
- `--until`/`--since` accept datetimes with any UTC offset; a datetime is an exact instant.
- Pre-filter no longer assumes JSON spacing or field order.
- `--from` with `--project` also matches the salted mask of the given name.
- `sleep` detected by the first word of each sub-command (quoted text ignored); bare `token-autopsy [options]` means `scan`.

## 0.1.0 (external-review fixes, Issue #1)
- No summed percentage of the three rules; each rule is flagged as overlapping, and `rules` prints a de-duplicated bound (each call counted once, priority d1 > d2 > d3 > d4).
- Every savings figure labelled "modelled estimate, not measured"; notes that numbers come from one machine's sample and that cache hits are not waste in themselves.
- Privacy wording: no raw conversation content is written; session ids and timestamps are kept. Package description: Claude Code only.
- README repositioned: actionable usage patterns, not another token dashboard.

## 0.1.0 (post-review fixes)
- Per-model list prices (dated), separate 5-minute and 1-hour cache-write pricing.
- Cost of parallel tool calls is split per tool; file-hunting runs must span 3+ distinct API calls.
- Subagent base cost capped by real cache-read spend; d3 saving marked as an assumed constant.
- Rules totals clamped (lower <= upper <= 95%).
- `--from` now applies `--since/--until/--project`; empty argv no longer reads `sys.argv`.
- Messages without id are not merged; empty and same-call commands ignored for repeat detection; stray `subagents` directory no longer becomes a fake session.
- Project-name masking uses a per-machine random salt.

## 0.1.0 - 2026-10-23
- First release: `scan`, `report` (text/Markdown/JSON, English or Traditional Chinese), `rules`.
- Claude Code logs only (`~/.claude/projects`). Codex support is planned for 0.2.
- Categories: cache re-read vs new input vs output, context-length buckets, subagent/main base re-read, polling (sleep loops and repeats within 60 s), >20k outputs, file-hunting, top 10 sessions.
- Project directory names are masked by default; `--show-paths` reveals them. No network access.
