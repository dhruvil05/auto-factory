"""A stand-in agent CLI for runner tests. It reads the prompt (stdin, or the file
named as its argument), works out the job and role from the header, and writes
the file that role must leave, like a well-behaved agent.

Behaviour can be steered per issue with $FAKE_AGENT_PLAN (a JSON file):
  {"<issue>": {"intake": "ACCEPT low none", "dry_fail_once": true,
               "reviews": {"code": ["CHANGES", "PASS"]}, "approve": "APPROVE",
               "reviewer_edits_code": true, "silent": ["spec-writer"]}}
It prints a Claude-style JSON result so the runner can record a cost. With
$FAKE_CODEX_HOME set it acts like Codex instead: it keeps a session file under
<that>/sessions/YYYY/MM/DD/ with running token counts and prints plain text.
"""

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path


class CodexSession:
    """A Codex-like session file: the task first, then token_count events with running totals."""

    def __init__(self, home, prompt_text):
        self.id = str(uuid.uuid4())
        now = time.localtime()
        d = Path(home) / "sessions" / time.strftime("%Y/%m/%d", now)
        d.mkdir(parents=True, exist_ok=True)
        self.file = d / f"rollout-{time.strftime('%Y-%m-%dT%H-%M-%S', now)}-{self.id}.jsonl"
        self.turns = 0
        self.write({"type": "session_meta", "payload": {"session_id": self.id, "model": "fake-flash"}})
        self.write({"type": "turn_context", "payload": {"model": "fake-flash"}})
        self.write({"type": "event_msg", "payload": {"type": "item_completed", "item": {
            "type": "UserMessage", "content": [{"type": "input_text", "text": prompt_text}]}}})

    def write(self, entry):
        with self.file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def turn(self):
        self.turns += 1
        n = self.turns
        self.write({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {
            "input_tokens": 10000 * n, "cached_input_tokens": 8000 * n, "cache_write_input_tokens": 0,
            "output_tokens": 500 * n, "reasoning_output_tokens": 100 * n, "total_tokens": 10500 * n}}}})


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def main():
    prompt = Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else sys.stdin.read()
    lines = prompt.splitlines()
    at = next(i for i, l in enumerate(lines) if l.startswith("Job: "))  # the "## This job" block, at the end
    head = lines[at]
    folder = Path(re.search(r"Job folder: (.+?)/\. Main checkout", head).group(1))
    worktree = Path(re.search(r"Worktree: (.+?)\. Branch:", head).group(1))
    issue = re.search(r"Issue: #(\d+)\.", head).group(1)
    role = re.search(r"^Role: ([\w-]+)\.$", prompt, re.M).group(1)
    task = lines[at + 2]
    if os.environ.get("FAKE_AGENT_TASKS"):  # tests can see exactly what each agent was asked
        with open(os.environ["FAKE_AGENT_TASKS"], "a", encoding="utf-8") as f:
            f.write(f"{role}\t{task}\n")
    plan_file = os.environ.get("FAKE_AGENT_PLAN")
    plan = json.loads(Path(plan_file).read_text(encoding="utf-8")).get(issue, {}) if plan_file else {}
    state_file = folder / f"fake-calls-{role}.txt"  # one file per role: reviewers run in parallel
    calls = {role: (int(state_file.read_text()) if state_file.exists() else 0) + 1}
    state_file.write_text(str(calls[role]), encoding="utf-8")
    reply = ""
    codex = (CodexSession(os.environ["FAKE_CODEX_HOME"], sys.argv[1] if len(sys.argv) > 1 else prompt)
             if os.environ.get("FAKE_CODEX_HOME") else None)
    if codex:
        codex.turn()

    if calls[role] == 1 and role in plan.get("sleep_once", {}):  # a long first run, to pause or stop it
        time.sleep(plan["sleep_once"][role])
    if role in plan.get("tool_error", []) or (calls[role] == 1 and role in plan.get("tool_error_once", [])):
        print(json.dumps({"type": "result", "result": "Failed to authenticate: session expired",
                          "total_cost_usd": 0, "is_error": True}))
        sys.exit(1)
    if role in plan.get("silent", []):
        reply = "done"
    elif role == "intake":
        decision, risk, surfaces = plan.get("intake", "ACCEPT low none").split()
        (folder / "intake.md").write_text(
            f"DECISION: {decision}\nRISK: {risk}\nSURFACES: {surfaces}\nRESCOPED: no\n\n## Summary\n- fake intake\n\n"
            "## Scope\nDo it.\n\n## Why\nFine.\n", encoding="utf-8")
        reply = f"DECISION: {decision}"
    elif role == "spec-writer":
        (folder / "spec.md").write_text("# Fake spec\n\n> Issue\n\n## Summary\n- a spec\n", encoding="utf-8")
        reply = "SPEC: Fake spec"
    elif role == "implementer" and plan.get("no_git"):
        # A sandboxed tool (like Codex) that can't write .git: change files, never commit.
        n = int(re.search(r"Implement round (\d+)", task).group(1))
        if plan["no_git"] == "blocked" and calls[role] == 2:  # the runner committed; re-check the status
            text = (folder / "impl.md").read_text(encoding="utf-8").replace("STATUS: BLOCKED", "STATUS: READY", 1)
            (folder / "impl.md").write_text(text.split("## Blocked")[0], encoding="utf-8")
            reply = "STATUS: READY"
        else:
            app = worktree / "app.txt"
            app.write_text(app.read_text(encoding="utf-8") + "sandboxed change\n", encoding="utf-8")
            (worktree / "test_new.py").write_text("def test_it():\n    assert True\n", encoding="utf-8")
            (worktree / ".env").write_text("SECRET=local-only\n", encoding="utf-8")
            if plan["no_git"] == "blocked":
                (folder / "impl.md").write_text(
                    f"STATUS: BLOCKED\n\n# Implementation\n\n## Summary\n- round {n}\n\n## Blocked\n"
                    "- fatal: Unable to create '.git/worktrees/x/index.lock': Permission denied, so no commit "
                    "can be created.\n", encoding="utf-8")
                reply = "STATUS: BLOCKED"
            else:
                (folder / "impl.md").write_text(f"STATUS: READY\n\n# Implementation\n\n## Summary\n- round {n}\n",
                                                encoding="utf-8")
                reply = "STATUS: READY"
    elif role == "implementer":
        n = int(re.search(r"Implement round (\d+)", task).group(1))
        fail_file = worktree / "FAIL"
        if plan.get("dry_fail_once") and calls[role] == 1:
            fail_file.write_text("x", encoding="utf-8")
            git(worktree, "add", "FAIL")
        elif fail_file.exists():
            fail_file.unlink()
            git(worktree, "rm", "-q", "--cached", "FAIL")
        app = worktree / "app.txt"
        app.write_text(app.read_text(encoding="utf-8") + f"change {calls[role]}\n", encoding="utf-8")
        git(worktree, "add", "app.txt")
        git(worktree, "commit", "-q", "-m", f"round {n} change")
        (folder / "impl.md").write_text(f"STATUS: READY\n\n# Implementation\n\n## Summary\n- round {n}\n", encoding="utf-8")
        reply = "STATUS: READY"
    elif role.startswith("reviewer-"):
        r = role.split("-", 1)[1]
        n = int(re.search(r"Review round (\d+)", task).group(1))
        verdicts = plan.get("reviews", {}).get(r, ["PASS"])
        verdict = verdicts[min(n, len(verdicts)) - 1]
        if plan.get("reviewer_edits_code"):
            (worktree / "app.txt").write_text("reviewer was here\n", encoding="utf-8")
        out = folder / f"round-{n}" / f"review-{r}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"VERDICT: {verdict}\n\n## Summary\n- fake review\n", encoding="utf-8")
        reply = f"VERDICT: {verdict}"
    elif role == "approver":
        decision = plan.get("approve", "APPROVE")
        (folder / "decision.md").write_text(f"{decision}\n\n## Summary\n- fake decision\n", encoding="utf-8")
        reply = decision
    if codex:
        codex.turn()  # two turns in all: 20,000 input (16,000 cached) and 1,000 output
        print(f"OpenAI Codex (fake)\nsession id: {codex.id}\nworking\ntokens used\n5,000\n{reply}")
        return
    print(json.dumps({"type": "result", "result": f"working…\n{reply}", "total_cost_usd": 0.01, "is_error": False}))


if __name__ == "__main__":
    main()
