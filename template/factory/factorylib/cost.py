"""API-equivalent cost of a job's agents, read from Claude Code's transcripts.

Claude Code keeps each subagent's messages under
<config>/projects/<project>/<session>/subagents/agent-<id>.jsonl, with an
agent-<id>.meta.json beside it that names the agent type. Every factory prompt
starts with `Job: <id>.`, which ties a transcript to its job. The format isn't a
documented interface, so anything unexpected makes the cost partial, never an error.
"""

import json
import os
import re
import time
from pathlib import Path

from . import paths, usage
from .files import atomic_write


def transcripts_dir():
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    return base / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(paths.REPO))


def _prompt(line):
    content = json.loads(line).get("message", {}).get("content", "")
    if isinstance(content, str):
        return content
    return " ".join(b.get("text", "") for b in content if isinstance(b, dict))


def _price(prices, model):
    return usage.price_for(prices, model)


LIVE_FRESH = 30  # seconds: a .live file the runner stopped rewriting is left over, not running


def _backfill(rec_file, rec):
    """Records written before the runner kept exact usage: read it from the Codex session the
    log names, once, and save it in the record (None when there is none)."""
    if "usage" in rec or rec.get("harness") is None:
        return rec.get("usage")
    found = None
    try:
        log = paths.job_dir(rec_file.parent.parent.name) / (rec.get("log") or "")
        if log.is_file():
            with log.open(encoding="utf-8", errors="replace") as f:
                session = usage.session_from_output(f.read(8192))
            found = usage.codex_usage(session) if session else None
    except OSError:
        found = None
    rec["usage"] = found
    if found:
        rec["tokens"] = usage.total(found)
    try:
        atomic_write(rec_file, json.dumps(rec, indent=2) + "\n")
    except OSError:
        pass
    return found


def runner_summary(job_id, prices):
    """Tokens and cost of the agents the runner started (runs/*.json), plus the ones running now
    (runs/*.live). Cost comes from the tool when it reports one (Claude Code), else from the
    tokens and Settings → Prices."""
    runs = paths.job_dir(job_id) / "runs"
    agents, live, unpriced = {}, [], set()
    totals = {"input": 0, "cached": 0, "output": 0, "total": 0}
    usd, partial, count = 0.0, False, 0
    recs = []
    for f in sorted(runs.glob("*.json")) if runs.exists() else []:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            partial = True
            continue
        if isinstance(rec, dict) and rec.get("role"):
            recs.append((f.stem, rec, _backfill(f, rec), False))
    done = {stem for stem, *_ in recs}
    now = time.time()
    for f in sorted(runs.glob("*.live")) if runs.exists() else []:
        try:
            if f.stem in done or now - f.stat().st_mtime > LIVE_FRESH:
                continue
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        recs.append((f.stem, rec, rec.get("usage"), True))
    for stem, rec, u, running in recs:
        role = rec.get("role", "agent")
        a = agents.setdefault(role, {"runs": 0, "tokens": 0, "input": 0, "cached": 0, "output": 0,
                                     "usd": 0.0, "priced": True, "model": None, "exact": True})
        a["runs"] += 1
        count += 1
        model = (u or {}).get("model") or (rec.get("model") if rec.get("model") not in (None, "(tool default)") else None)
        a["model"] = model or a["model"]
        if u:
            tok = usage.total(u)
            for k in ("input", "cached", "output"):
                a[k] += u.get(k) or 0
                totals[k] += u.get(k) or 0
        else:
            tok = rec.get("tokens") if isinstance(rec.get("tokens"), int) else 0
            a["exact"] = a["exact"] and running  # an old count without cached input is too low
        a["tokens"] += tok
        totals["total"] += tok
        cost = rec.get("cost_usd") if isinstance(rec.get("cost_usd"), (int, float)) else None
        if cost is None and u:
            p = _price(prices, model)
            cost = usage.cost_of(u, p) if p else None
            if p is None:
                unpriced.add(model or rec.get("harness") or "unknown model")
        if cost is None:
            if not running:
                partial = True
                a["priced"] = False
        else:
            usd += cost
            a["usd"] += cost
        if running:
            live.append({"role": role, "started": rec.get("started"), "tokens": tok,
                         "usd": round(cost, 4) if cost is not None else None, "model": model})
    for a in agents.values():
        a["usd"] = round(a["usd"], 4)
    return {"usd": usd, "partial": partial, "runs": count, "agents": agents, "tokens": totals,
            "live": live, "unpriced": sorted(unpriced)}


def runner_costs(job_id, prices=None):
    """(total, {role: usd}, partial) for the runner's agent calls."""
    s = runner_summary(job_id, prices or {})
    return s["usd"], {r: a["usd"] for r, a in s["agents"].items() if a["priced"] or a["usd"]}, s["partial"]


def _result(total, by_agent, partial, summary):
    return {"usd": round(total, 2), "by_agent": {k: round(v, 2) for k, v in by_agent.items()}, "partial": partial,
            "exact_usd": round(total, 4), "tokens": summary["tokens"], "agents": summary["agents"],
            "live": summary["live"], "unpriced": summary["unpriced"]}


def job_cost(job_id, prices, transcripts=True):
    """The job's cost and tokens. transcripts=False skips Claude Code's transcripts (the /factory
    skill's agents): cheap enough for the dashboard to call every few seconds."""
    needle = f"Job: {job_id}."
    summary = runner_summary(job_id, prices)
    total, partial = summary["usd"], summary["partial"]
    by_agent = {r: a["usd"] for r, a in summary["agents"].items() if a["priced"] or a["usd"]}
    root = transcripts_dir()
    if not transcripts or not root.exists():
        return _result(total, by_agent, partial, summary)
    for path in root.glob("*/subagents/agent-*.jsonl"):
        try:
            with path.open(encoding="utf-8", errors="replace") as f:
                first = f.readline()
                if not first or needle not in _prompt(first):
                    continue
                usage = {}
                for line in f:
                    entry = json.loads(line)
                    msg = entry.get("message")
                    if entry.get("type") == "assistant" and isinstance(msg, dict) and msg.get("usage"):
                        usage[msg.get("id") or len(usage)] = (msg.get("model", ""), msg["usage"])
            meta = path.with_name(path.stem + ".meta.json")
            agent = json.loads(meta.read_text(encoding="utf-8")).get("agentType", "agent") if meta.exists() else "agent"
        except (OSError, ValueError):
            partial = True
            continue
        cost = 0.0
        for model, u in usage.values():
            p = _price(prices, model)
            if p is None:
                partial = True
                continue
            write_1h = (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens", 0)
            write_5m = u.get("cache_creation_input_tokens", 0) - write_1h
            cost += (u.get("input_tokens", 0) * p["input"] + u.get("output_tokens", 0) * p["output"]
                     + write_5m * p.get("cache_write_5m", p["input"]) + write_1h * p.get("cache_write_1h", p["input"])
                     + u.get("cache_read_input_tokens", 0) * p.get("cache_read", p["input"])) / 1e6
        total += cost
        by_agent[agent] = round(by_agent.get(agent, 0.0) + cost, 4)
    return _result(total, by_agent, partial, summary)
