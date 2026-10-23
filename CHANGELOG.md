# Changelog

## 0.1.0 - 2026-10-23
- First release: `scan`, `report` (text/Markdown/JSON, English or Traditional Chinese), `rules`.
- Claude Code logs only (`~/.claude/projects`). Codex support is planned for 0.2.
- Categories: cache re-read vs new input vs output, context-length buckets, subagent/main base re-read, polling (sleep loops and repeats within 60 s), >20k outputs, file-hunting, top 10 sessions.
- Project directory names are masked by default; `--show-paths` reveals them. No network access.
