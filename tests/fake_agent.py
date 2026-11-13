"""A stand-in agent CLI for runner tests. It reads the prompt (stdin, or the file
named as its argument), works out the job and role from the header, and writes
the file that role must leave, like a well-behaved agent.

Behaviour can be steered per issue with $FAKE_AGENT_PLAN (a JSON file):
  {"<issue>": {"intake": "ACCEPT low none", "dry_fail_once": true,
               "reviews": {"code": ["CHANGES", "PASS"]}, "approve": "APPROVE",
               "reviewer_edits_code": true, "silent": ["spec-writer"]}}
It prints a Claude-style JSON result so the runner can record a cost.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


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

    if role in plan.get("tool_error", []):
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
    print(json.dumps({"type": "result", "result": f"working…\n{reply}", "total_cost_usd": 0.01, "is_error": False}))


if __name__ == "__main__":
    main()
