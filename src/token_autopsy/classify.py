"""Classify tool calls into coarse kinds without retaining any command text.

Kinds: poll (sleep loop), browse (discovery: ls/find/grep/rg/Glob/Grep),
shread (cat/head/git log... via shell), read (Read tool), edit (writing files), other.
The command text is inspected in memory only; callers keep just the kind and an
opaque hash used to detect repeated commands.
"""
from __future__ import annotations

import hashlib
import re

SLEEP_RE = re.compile(r"(?:^|[;&|\s(`])sleep\s+(\d+(?:\.\d+)?)([smhd]?)")
SPLIT_RE = re.compile(r"&&|\|\||;|\||\n")
BROWSE_CMDS = {"ls", "find", "grep", "egrep", "fgrep", "rg", "tree", "fd", "ag", "locate", "ack"}
READ_CMDS = {"cat", "head", "tail", "less", "more", "bat", "nl", "wc", "stat", "file"}
GIT_BROWSE = {"ls-files", "grep"}
GIT_READ = {"log", "status", "diff", "show", "blame", "branch"}
BROWSE_TOOLS = {"Glob", "Grep", "LS", "ToolSearch"}
READ_TOOLS = {"Read", "NotebookRead", "WebFetch", "WebSearch"}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_MULT = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}


_KEYWORDS = {"do", "then", "else", "elif", "while", "until", "if", "!", "{", "(", "time", "exec"}
_QUOTED = re.compile(r"\"(?:\\.|[^\"\\])*\"|'[^']*'")


def _first_words(cmd: str):
    """Yield the words of each sub-command, after dropping shell keywords and leading cd/env."""
    cmd = _QUOTED.sub('""', cmd)
    for part in SPLIT_RE.split(cmd):
        words = part.strip().lstrip("$(`{").split()
        while words and (words[0] in _KEYWORDS or words[0] in ("export", "env", "sudo")
                         or "=" in words[0].split("/")[0]):
            words = words[1:]
        if words and words[0] == "cd":
            continue
        if words:
            yield words


def _sleep_args(words) -> float:
    total, ok = 0.0, False
    for w in words[1:]:
        m = re.fullmatch(r"(\d+(?:\.\d+)?)([smhd]?)", w)
        if m:
            total += float(m.group(1)) * _MULT[m.group(2)]
            ok = True
        elif ok or not w.startswith("$"):
            break
    return total


def sleep_seconds(cmd: str) -> float:
    return sum(_sleep_args(w) for w in _first_words(cmd) if w[0] == "sleep")


def is_sleep(cmd: str) -> bool:
    return any(w[0] == "sleep" and len(w) > 1 for w in _first_words(cmd))


def classify_bash(cmd: str) -> tuple[str, float]:
    """Return (kind, sleep_seconds)."""
    if is_sleep(cmd):
        return "poll", sleep_seconds(cmd)
    kinds = set()
    for words in _first_words(cmd):
        w = words[0].rsplit("/", 1)[-1]
        if w in BROWSE_CMDS or (w == "git" and len(words) > 1 and words[1] in GIT_BROWSE):
            kinds.add("browse")
        elif w in READ_CMDS or (w == "sed" and "-n" in words) or \
                (w == "git" and len(words) > 1 and words[1] in GIT_READ):
            kinds.add("shread")
        elif w in ("apply_patch", "tee"):
            kinds.add("edit")
        else:
            kinds.add("other")
    if "edit" in kinds:
        return "edit", 0.0
    if "shread" in kinds:
        return "shread", 0.0
    if kinds == {"browse"}:
        return "browse", 0.0
    if "browse" in kinds and "other" not in kinds:
        return "browse", 0.0
    return "other", 0.0


def cmd_key(cmd: str) -> str:
    return hashlib.sha1(" ".join(cmd.split()).encode("utf-8", "replace")).hexdigest()[:12]


def classify_tool(name: str, inp) -> tuple[str, str | None, float]:
    """Return (kind, repeat_key_or_None, sleep_seconds) for a Claude Code tool_use."""
    if name == "Bash":
        cmd = inp.get("command", "") if isinstance(inp, dict) else ""
        kind, secs = classify_bash(cmd)
        return kind, (cmd_key(cmd) if cmd.strip() else None), secs
    if name in BROWSE_TOOLS:
        return "browse", None, 0.0
    if name in READ_TOOLS:
        return "read", None, 0.0
    if name in EDIT_TOOLS:
        return "edit", None, 0.0
    return "other", None, 0.0
