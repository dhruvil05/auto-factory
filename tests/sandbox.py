"""A throwaway project with a bare `origin`, the factory installed, and a fake gh."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
PY = sys.executable
PASS_CMD = f'"{PY}" -c "import pathlib,sys; sys.exit(1 if pathlib.Path(\'FAIL\').exists() else 0)"'


class Sandbox:
    def __init__(self, checks=None, **config_overrides):
        self.tmp = Path(tempfile.mkdtemp(prefix="af-test-"))
        self.origin = self.tmp / "origin.git"
        self.repo = self.tmp / "proj app"  # a space, like real Windows paths
        self.gh_state = self.tmp / "gh.json"
        self.env = dict(os.environ)
        self.env.update({
            "FACTORY_GH": str(HERE / "fake_gh.py"),
            "FAKE_GH_STATE": str(self.gh_state),
            "CLAUDE_CONFIG_DIR": str(self.tmp / "claude"),
            "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.test",
            "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.test",
        })
        self.env.pop("FACTORY_REPO", None)
        self.gh_state.write_text(json.dumps({"issues": {}, "prs": {}}), encoding="utf-8")
        self.git(self.tmp, "init", "--bare", "-b", "main", str(self.origin))
        self.git(self.tmp, "clone", str(self.origin), str(self.repo))
        (self.repo / "README.md").write_text("# app\n", encoding="utf-8")
        (self.repo / "app.txt").write_text("orders list\n", encoding="utf-8")
        self.git(self.repo, "add", "README.md", "app.txt")
        self.git(self.repo, "commit", "-m", "start")
        self.git(self.repo, "push", "-u", "origin", "main")
        self.run([PY, str(PACKAGE / "install.py"), str(self.repo)])
        cfg = self.config()
        cfg["checks"] = checks if checks is not None else [
            {"name": "tests", "cmd": PASS_CMD, "enabled": True, "timeout": 60, "retry_on_fail": 0}]
        cfg.update(config_overrides)
        self.write_config(cfg)
        self.git(self.repo, "add", "-A")
        self.git(self.repo, "commit", "-m", "install factory")
        self.git(self.repo, "push")

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- running things --
    def run(self, cmd, cwd=None, stdin=None, check=True):
        res = subprocess.run(cmd, cwd=str(cwd or self.repo), env=self.env, input=stdin, capture_output=True,
                             text=True, encoding="utf-8", errors="replace")
        if check and res.returncode != 0:
            raise AssertionError(f"{cmd} failed ({res.returncode}):\n{res.stdout}\n{res.stderr}")
        return res

    def git(self, cwd, *args):
        return self.run(["git", *args], cwd=cwd)

    def script(self, name, *args, stdin=None, check=True):
        return self.run([PY, str(self.repo / "factory" / "bin" / f"{name}.py"), *args], stdin=stdin, check=check)

    def job(self, *args, **kw):
        return self.script("job", *args, **kw)

    # -- config and state --
    def config(self):
        return json.loads((self.repo / "factory" / "config.json").read_text(encoding="utf-8"))

    def write_config(self, cfg):
        (self.repo / "factory" / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    def gh(self):
        return json.loads(self.gh_state.read_text(encoding="utf-8"))

    def put_gh(self, s):
        self.gh_state.write_text(json.dumps(s), encoding="utf-8")

    def add_issue(self, n, title, body="Please do it.", labels=("factory",), author="ops-lead"):
        s = self.gh()
        s["issues"][str(n)] = {"number": n, "title": title, "body": body, "state": "OPEN",
                               "url": f"https://example.test/issues/{n}", "author": {"login": author},
                               "labels": [{"name": lb} for lb in labels], "comments": []}
        self.put_gh(s)

    def jobdir(self, job_id):
        return self.repo / "factory" / "jobs" / job_id

    def jobjson(self, job_id):
        return json.loads((self.jobdir(job_id) / "job.json").read_text(encoding="utf-8"))

    def write(self, job_id, rel, text):
        p = self.jobdir(job_id) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    # -- pretend agents --
    def intake(self, job_id, decision="ACCEPT", risk="low", surfaces="none"):
        self.write(job_id, "intake.md", f"DECISION: {decision}\nRISK: {risk}\nSURFACES: {surfaces}\nRESCOPED: no\n\n"
                                        "## Summary\n- Clear request\n\n## Scope\nAdd the filter.\n\n## Why\nFits.\n")

    def implement(self, job_id, files, first=True, status="READY"):
        """Commit `files` ({path: text}) in the worktree, push, open the draft PR the first time."""
        job = self.jobjson(job_id)
        wt = Path(job["worktree"])
        for rel, text in files.items():
            p = wt / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if text is None:
                p.unlink()
            else:
                p.write_text(text, encoding="utf-8")
        self.git(wt, "add", "-A")
        self.git(wt, "commit", "-m", "work")
        self.git(wt, "push", "-u", "origin", job["branch"])
        if first:
            self.run([PY, str(HERE / "fake_gh.py"), "pr", "create", "--draft", "--base", "main",
                      "--head", job["branch"], "--title", job["title"], "--body", f"Closes #{job['issue']}"])
        self.write(job_id, "impl.md", f"STATUS: {status}\n\n# Implementation\n\n## Summary\n- Did it\n\n"
                                      + ("## Blocked\nNeeds a decision.\n" if status == "BLOCKED" else ""))

    def to_review(self, job_id, files=None):
        """intake ACCEPT (low) → … → review, gate passing."""
        self.intake(job_id)
        self.script("route", job_id)
        self.job("advance", job_id, "spec")
        self.write(job_id, "spec.md", "# Filter\n\n> Issue #1: x\n\n## Summary\n- a\n")
        self.job("advance", job_id, "implement")
        self.implement(job_id, files or {"app.txt": "orders list\nstatus filter\n"})
        self.job("advance", job_id, "gate")
        assert self.script("gate", job_id).returncode == 0
        self.job("advance", job_id, "review")
