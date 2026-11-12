"""run.py, the tool-neutral runner, driving a fake agent CLI end to end."""

import json
import unittest
from pathlib import Path

from sandbox import HERE, PY, Sandbox

FAKE = HERE / "fake_agent.py"


class RunnerTest(unittest.TestCase):
    def make(self, plan=None, prompt="stdin", auto_merge=False, concurrency=1, **runner):
        self.sb = Sandbox()
        cfg = self.sb.config()
        cfg["concurrency"] = concurrency
        cfg["routing"]["low"]["auto_merge"] = auto_merge
        cmd = f'"{PY}" "{FAKE}"' + (' "{PROMPT_FILE}"' if prompt == "file" else "")
        cfg["runner"]["harnesses"]["fake"] = {"cmd": cmd, "prompt": prompt, "output": "claude-json",
                                              "model_flag": "", "models": {}, "verified": True}
        cfg["runner"]["harness"] = "fake"
        cfg["runner"].update(runner)
        self.sb.write_config(cfg)
        if plan is not None:
            p = self.sb.tmp / "plan.json"
            p.write_text(json.dumps(plan), encoding="utf-8")
            self.sb.env["FAKE_AGENT_PLAN"] = str(p)

    def tearDown(self):
        self.sb.close()

    def run_factory(self, *args, check=True):
        return self.sb.script("run", *args, check=check)

    def runs(self, job_id):
        d = self.sb.jobdir(job_id) / "runs"
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))]

    def test_issue_to_held_pr(self):
        self.make()
        self.sb.add_issue(1, "Add a status filter to orders")
        out = self.run_factory().stdout
        job = self.sb.jobjson("001-add-a-status-filter")
        self.assertEqual(job["stage"], "needs-human", out)
        self.assertTrue(job["held"])
        roles = [r["role"] for r in self.runs(job["id"])]
        self.assertEqual(roles, ["intake", "spec-writer", "implementer", "reviewer-code", "approver"])
        self.assertIn("opened draft PR", out)          # the fake agent can't push; the runner did
        pr = self.sb.gh()["prs"][str(job["pr"])]
        self.assertFalse(pr["isDraft"])
        self.assertEqual(job["cost"]["usd"], 0.05)
        self.assertEqual(job["cost"]["by_agent"]["implementer"], 0.01)
        self.assertIn("Waiting on people", out)
        prompt = (self.sb.jobdir(job["id"]) / "runs" / "003-implementer.prompt.md").read_text(encoding="utf-8")
        self.assertTrue(prompt.startswith(f"Job: {job['id']}. Job folder: "))
        self.assertIn("Role: implementer.\nImplement round 1.", prompt)
        self.assertIn("## How this run works", prompt)
        self.assertNotIn("hooks:", prompt)              # frontmatter is stripped

    def test_auto_merge_and_prompt_file_mode(self):
        self.make(prompt="file", auto_merge=True)
        self.sb.add_issue(1, "Tiny change")
        self.run_factory()
        job = self.sb.jobjson("001-tiny-change")
        self.assertEqual(job["stage"], "merged")
        self.assertFalse(Path(job["worktree"]).exists())
        log = next((self.sb.jobdir(job["id"]) / "runs").glob("*-intake.log")).read_text(encoding="utf-8")
        self.assertIn("001-intake.prompt.md", log)  # the command named the prompt file

    def test_dry_gate_failure_gets_one_nudge(self):
        self.make(plan={"1": {"dry_fail_once": True}}, auto_merge=True)
        self.sb.add_issue(1, "Fix the totals")
        out = self.run_factory().stdout
        job = self.sb.jobjson("001-fix-the-totals")
        self.assertIn("dry gate failed", out)
        self.assertEqual([r["role"] for r in self.runs(job["id"])].count("implementer"), 2)
        self.assertEqual(job["stage"], "merged")
        self.assertEqual(job["round"], 1)

    def test_review_changes_then_pass(self):
        self.make(plan={"1": {"intake": "ACCEPT medium ui", "reviews": {"ux": ["CHANGES", "PASS"]}}})
        self.sb.add_issue(1, "Status filter")
        self.run_factory()
        job = self.sb.jobjson("001-status-filter")
        self.assertEqual(job["round"], 2)
        self.assertEqual(job["stage"], "needs-human")  # medium risk: held for a human merge
        roles = [r["role"] for r in self.runs(job["id"])]
        self.assertEqual(roles.count("reviewer-ux"), 2)
        self.assertEqual(roles.count("reviewer-code"), 2)
        self.assertIn("Round 1 reviews are in round-1/", self.runs(job["id"])[
            [i for i, r in enumerate(roles) if r == "implementer"][1]]["task"])

    def test_reviewer_editing_code_is_reverted(self):
        self.make(plan={"1": {"reviewer_edits_code": True}})
        self.sb.add_issue(1, "Thing")
        self.run_factory()
        job = self.sb.jobjson("001-thing")
        warnings = (self.sb.jobdir(job["id"]) / "runs" / "warnings.md").read_text(encoding="utf-8")
        self.assertIn("reviewer-code changed the code", warnings)
        self.assertEqual(job["stage"], "needs-human")

    def test_needs_info_and_reject_stop_cleanly(self):
        self.make(plan={"1": {"intake": "NEEDS-INFO low none"}, "2": {"intake": "REJECT high none"}}, concurrency=2)
        self.sb.add_issue(1, "Make reports better")
        self.sb.add_issue(2, "Disable the audit log")
        out = self.run_factory().stdout
        self.assertEqual(self.sb.jobjson("001-make-reports-better")["stage"], "needs-info")
        self.assertEqual(self.sb.jobjson("002-disable-the-audit-log")["stage"], "rejected")
        self.assertIn("waiting for the author", out)

    def test_agent_that_writes_nothing_is_asked_again_then_stopped(self):
        self.make(plan={"1": {"silent": ["spec-writer"]}})
        self.sb.add_issue(1, "Thing")
        r = self.run_factory(check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("spec-writer didn't write spec.md after two tries", r.stdout)
        job = self.sb.jobjson("001-thing")
        self.assertEqual(job["stage"], "spec")
        self.assertTrue((self.sb.jobdir(job["id"]) / "runs" / "stopped.md").exists())

    def test_tool_error_stops_without_retry(self):
        self.make(plan={"1": {"tool_error": ["intake"]}})
        self.sb.add_issue(1, "Thing")
        r = self.run_factory(check=False)
        self.assertIn("intake (fake) failed: Failed to authenticate: session expired", r.stdout)
        self.assertEqual(len(self.runs("001-thing")), 1)  # no pointless second try

    def test_per_role_tool(self):
        self.make()
        cfg = self.sb.config()
        cfg["runner"]["harnesses"]["fake2"] = dict(cfg["runner"]["harnesses"]["fake"])
        cfg["runner"]["role_harness"] = {"intake": "fake2"}
        self.sb.write_config(cfg)
        self.sb.add_issue(1, "Thing")
        self.run_factory()
        runs = self.runs("001-thing")
        self.assertEqual(runs[0]["harness"], "fake2")
        self.assertEqual(runs[1]["harness"], "fake")

    def test_paused_and_red_main_start_nothing(self):
        self.make()
        self.sb.add_issue(1, "Thing")
        self.sb.job("pause")
        self.assertIn("paused", self.run_factory(check=False).stdout)
        self.sb.job("unpause")
        cfg = self.sb.config()
        cfg["checks"][0]["cmd"] = f'"{PY}" -c "import sys; sys.exit(1)"'
        self.sb.write_config(cfg)
        r = self.run_factory(check=False)
        self.assertIn("nothing starts", r.stdout)
        self.assertFalse((self.sb.repo / "factory" / "jobs" / "001-thing").exists())

    def test_doctor(self):
        self.make()
        cfg = self.sb.config()
        cfg["runner"]["role_harness"] = {"approver": "codex"}
        self.sb.write_config(cfg)
        r = self.run_factory("doctor", check=False)
        self.assertIn("fake: found", r.stdout)
        self.assertIn("preset not verified", r.stdout)
        self.assertIn("codex: ", r.stdout)


if __name__ == "__main__":
    unittest.main()
