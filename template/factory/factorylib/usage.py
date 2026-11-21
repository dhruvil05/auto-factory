"""Token usage of one agent run, as exact as the agent tool reports it.

usage = {"input": all input tokens (cached ones included), "cached": input read from the
provider's cache, "cache_write": input written to it (Claude), "output": output tokens
(reasoning included), "model": the model the tool really used, or None}

- Claude Code (`--output-format json`): the `usage` block of its result line.
- Codex: its own session file, ~/.codex/sessions/YYYY/MM/DD/rollout-…-<session id>.jsonl
  (or under $CODEX_HOME). Its `token_count` events carry running totals, so the file
  also gives live numbers while the agent works. Codex's closing "tokens used" line
  leaves out cached input, which is most of what a long run sends.
The formats aren't documented interfaces: anything unexpected means "no usage", never an error.
"""

import json
import os
import re
import time
from pathlib import Path

TAIL = 512 * 1024    # token_count events are near the end; read only this much of a big file
HEAD = 256 * 1024    # the prompt, model and settings are near the start
SESSION_ID = re.compile(r"session id:\s*([0-9a-fA-F-]{36})")


def codex_home():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def _read(path, start, size):
    with open(path, "rb") as f:
        f.seek(start)
        return f.read(size).decode("utf-8", errors="replace")


def _head(path):
    return _read(path, 0, HEAD)


def _opening(path):
    """The session's start up to the task it was given (its first user message), so a later
    session that merely reads another job's files doesn't look like that job's run."""
    lines = []
    for line in _head(path).splitlines():
        lines.append(line)
        if '"UserMessage"' in line or '"function_call"' in line:
            break
    return "\n".join(lines)


def _tail(path):
    size = path.stat().st_size
    return _read(path, max(0, size - TAIL), TAIL)


def codex_usage(path):
    """Usage from a Codex session file, or None while it has no token count yet."""
    try:
        tail = _tail(path)
    except OSError:
        return None
    total = None
    for line in reversed(tail.splitlines()):
        if '"token_count"' not in line:
            continue
        try:
            info = (json.loads(line).get("payload") or {}).get("info") or {}
        except ValueError:
            continue  # the first line of a tail read can be cut
        total = info.get("total_token_usage")
        if isinstance(total, dict):
            break
        total = None
    if not total:
        return None
    model = None
    try:
        for line in _head(path).splitlines():
            if '"turn_context"' in line or '"session_meta"' in line:
                try:
                    payload = json.loads(line).get("payload") or {}
                except ValueError:
                    continue
                model = payload.get("model") or model
    except OSError:
        pass

    def n(k):
        v = total.get(k)
        return v if isinstance(v, int) and v >= 0 else 0

    return {"input": n("input_tokens"), "cached": n("cached_input_tokens"),
            "cache_write": n("cache_write_input_tokens"), "output": n("output_tokens"), "model": model}


def claude_usage(out):
    """Usage from Claude Code's JSON result line, or None."""
    for line in reversed(out.strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        u = data.get("usage")
        if not isinstance(u, dict):
            return None
        n = lambda k: u.get(k) if isinstance(u.get(k), int) else 0
        models = data.get("modelUsage")
        model = next(iter(models), None) if isinstance(models, dict) and len(models) == 1 else None
        return {"input": n("input_tokens") + n("cache_creation_input_tokens") + n("cache_read_input_tokens"),
                "cached": n("cache_read_input_tokens"), "cache_write": n("cache_creation_input_tokens"),
                "output": n("output_tokens"), "model": model}
    return None


def find_codex_session(session_id=None, since=None, needles=()):
    """The session file for a run: by the id Codex printed, or (while it runs, before any
    output) the newest file changed since `since` whose start holds every needle."""
    root = codex_home() / "sessions"
    if not root.is_dir():
        return None
    if session_id:
        hits = sorted(root.glob(f"*/*/*/rollout-*{session_id}.jsonl"))
        return hits[-1] if hits else None
    if since is None or not needles:
        return None
    days = {time.strftime("%Y/%m/%d", time.localtime(t)) for t in (since - 86400, since, time.time())}
    days |= {time.strftime("%Y/%m/%d", time.gmtime(t)) for t in (since, time.time())}
    cands = []
    for day in days:
        d = root / day
        if d.is_dir():
            for f in d.glob("rollout-*.jsonl"):
                if started_at(f) >= since - 2:  # an earlier run of the same role isn't this one
                    cands.append(f)
    for f in sorted(cands, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            head = _opening(f)
        except OSError:
            continue
        if all(any(alt in head for alt in (needle if isinstance(needle, tuple) else (needle,))) for needle in needles):
            return f
    return None


def started_at(f):
    """When a session began, from its file name (local time): rollout-2026-11-20T13-26-15-<id>.jsonl."""
    m = re.match(r"rollout-(\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d)", f.name)
    try:
        return time.mktime(time.strptime(m.group(1), "%Y-%m-%dT%H-%M-%S")) if m else 0
    except (ValueError, OverflowError):
        return 0


def session_from_output(out):
    m = SESSION_ID.search(out or "")
    return find_codex_session(m.group(1)) if m else None


def total(usage):
    return (usage.get("input") or 0) + (usage.get("output") or 0) if usage else 0


def price_for(prices, model):
    if not model or not isinstance(prices, dict):
        return None
    if model in prices:
        return prices[model]
    for key, p in prices.items():  # "claude-opus-5-5" also prices "claude-opus-5-5-20261101"
        if model.startswith(key):
            return p
    return None


def cost_of(usage, p):
    """USD for a usage at price `p` (USD per million tokens). Cached input costs `cache_read`,
    written cache `cache_write_5m`; both default to the input price when not set."""
    inp, out = p.get("input", 0), p.get("output", 0)
    read = p.get("cache_read", inp)
    write = p.get("cache_write_5m", inp)
    cached, written = usage.get("cached") or 0, usage.get("cache_write") or 0
    fresh = max(0, (usage.get("input") or 0) - cached - written)
    return (fresh * inp + cached * read + written * write + (usage.get("output") or 0) * out) / 1e6
