"""Read Claude Code transcripts (~/.claude/projects/**/*.jsonl).

Two quirks of the log format drive everything here:

1. One assistant message is written as SEVERAL lines (one per content block:
   thinking, text, tool_use...) and every line repeats the same `usage`.
   Summing lines inflates token counts 2-3x, so messages are deduplicated by
   `message.id` and the most complete usage (highest output_tokens) is kept.
2. Resuming a session copies earlier lines into a new file, so the same
   message id / tool_use block / prompt can appear in more than one file.
   Tool calls are deduplicated by block id, prompts by line uuid.

Only metadata is kept in memory: timestamps, model names, token counts, tool
names, project folder names. Message text is never stored or written out.
"""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from datetime import datetime

TOKEN_KINDS = ("input", "output", "cache_read", "cache_write")


@dataclass
class Message:
    id: str
    ts: datetime                     # local time, timezone-aware
    model: str
    project: str
    session: str
    sidechain: bool                  # written by a subagent
    tokens: dict
    cache_write_5m: int              # part of cache_write with the 5-minute TTL
    tools: dict = field(default_factory=dict)   # tool_use block id -> tool name


@dataclass
class Session:
    id: str
    project: str
    events: list = field(default_factory=list)  # timestamps of user/assistant lines


@dataclass
class Scan:
    messages: list
    sessions: dict
    prompts: list                    # timestamps of prompts typed by the user
    files: int
    bad_lines: int


def default_claude_dir() -> str:
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()


def _project_name(cwd, folder: str) -> str:
    if isinstance(cwd, str) and cwd:
        return os.path.basename(cwd.replace("\\", "/").rstrip("/")) or cwd
    return folder


def _is_typed_prompt(d: dict) -> bool:
    """A line the human actually typed (not a tool result, hook or slash-command echo)."""
    if d.get("type") != "user" or d.get("isMeta") or "toolUseResult" in d:
        return False
    origin = d.get("origin")
    if isinstance(origin, dict) and origin.get("kind"):   # newer Claude Code versions say it directly
        return origin["kind"] == "human"
    content = (d.get("message") or {}).get("content")
    if isinstance(content, list):
        kinds = {b.get("type") for b in content if isinstance(b, dict)}
        if "tool_result" in kinds or "text" not in kinds:
            return False
        content = next(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(content, str):
        return False
    text = content.lstrip()
    # "<command-name>", "<task-notification>", "<local-command-stdout>" ... are not typed by a human
    return bool(text) and not text.startswith("<") and not text.startswith("[Request interrupted")


def scan(claude_dir: str) -> Scan:
    root = os.path.join(claude_dir, "projects")
    msgs: dict[str, Message] = {}
    sessions: dict[str, Session] = {}
    prompts: list[datetime] = []
    seen_prompts: set = set()
    seen_events: set = set()
    files = bad = 0

    for path in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
        files += 1
        folder = os.path.relpath(path, root).split(os.sep)[0]
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                    when = parse_ts(d["timestamp"])
                except (ValueError, KeyError, TypeError, AttributeError):
                    bad += line.strip() != ""
                    continue
                kind = d.get("type")
                if kind not in ("user", "assistant"):
                    continue
                sid = d.get("sessionId") or ""
                project = _project_name(d.get("cwd"), folder)

                ev = d.get("uuid") or (sid, d["timestamp"], kind)
                if sid and ev not in seen_events:
                    seen_events.add(ev)
                    sessions.setdefault(sid, Session(sid, project)).events.append(when)

                if _is_typed_prompt(d):
                    if ev not in seen_prompts:
                        seen_prompts.add(ev)
                        prompts.append(when)
                    continue

                m = d.get("message")
                if kind != "assistant" or not isinstance(m, dict) or not isinstance(m.get("usage"), dict):
                    continue
                model = m.get("model") or ""
                if not model or model.startswith("<"):      # "<synthetic>" placeholder messages
                    continue
                u = m["usage"]
                tokens = {
                    "input": u.get("input_tokens") or 0,
                    "output": u.get("output_tokens") or 0,
                    "cache_read": u.get("cache_read_input_tokens") or 0,
                    "cache_write": u.get("cache_creation_input_tokens") or 0,
                }
                cw5 = (u.get("cache_creation") or {}).get("ephemeral_5m_input_tokens") or 0
                blocks = m.get("content") if isinstance(m.get("content"), list) else []
                tools = {b.get("id") or f"{d.get('uuid')}:{i}": b.get("name") or "?"
                         for i, b in enumerate(blocks)
                         if isinstance(b, dict) and b.get("type") == "tool_use"}

                key = m.get("id") or d.get("requestId") or d.get("uuid") or f"{path}:{when}"
                prev = msgs.get(key)
                if prev is None:
                    msgs[key] = Message(key, when, model, project, sid,
                                        bool(d.get("isSidechain")), tokens, cw5, tools)
                    continue
                # same message seen again: keep the most complete usage, merge tool blocks
                if tokens["output"] >= prev.tokens["output"]:
                    prev.tokens, prev.cache_write_5m = tokens, cw5
                prev.ts = min(prev.ts, when)
                prev.tools.update(tools)

    for s in sessions.values():
        s.events.sort()
    return Scan(list(msgs.values()), sessions, sorted(prompts), files, bad)


def retention_days(claude_dir: str):
    """cleanupPeriodDays from settings.json (Claude Code deletes older transcripts)."""
    try:
        with open(os.path.join(claude_dir, "settings.json"), encoding="utf-8") as fh:
            return json.load(fh).get("cleanupPeriodDays")
    except (OSError, ValueError, AttributeError):
        return None
