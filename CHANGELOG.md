# Changelog

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
