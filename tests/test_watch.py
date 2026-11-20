"""The runner in watch mode: it keeps going, picks up feedback and retries by itself,
lets one job be paused or stopped while others carry on, and is started and stopped
from the dashboard."""

import json
import socket
import subprocess
import time
import unittest
import urllib.error
import urllib.request

from sandbox import HERE, PY, Sandbox

FAKE = HERE / "fake_agent.py"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class WatchTest(unittest.TestCase):
    procs = ()

    def make(self, plan=None, auto_merge=False, concurrency=1):
        self.sb = Sandbox()
        self.procs = []
        cfg = self.sb.config()
        cfg["concurrency"] = concurrency
        cfg["routing"]["low"]["auto_merge"] = auto_merge
        cfg["runner"]["harnesses"]["fake"] = {"cmd": f'"{PY}" "{FAKE}"', "prompt": "stdin", "output": "claude-json",
                                              "model_flag": "", "models": {}, "verified": True}
        cfg["runner"]["harness"] = "fake"
        self.sb.write_config(cfg)
        self.sb.git(self.sb.repo, "commit", "-qam", "fake agent tool")
        self.sb.git(self.sb.repo, "push", "-q")
        p = self.sb.tmp / "plan.json"
        p.write_text(json.dumps(plan or {}), encoding="utf-8")
        self.sb.env["FAKE_AGENT_PLAN"] = str(p)
        self.sb.env["FAKE_AGENT_TASKS"] = str(self.sb.tmp / "tasks.tsv")

    def tearDown(self):
        if hasattr(self, "sb"):  # a runner the dashboard started lives in its own process group
            self.sb.script("run", "stop", "--now", check=False)
            for _ in range(50):
                if "runner: off" in self.sb.script("run", "status", check=False).stdout:
                    break
                time.sleep(0.2)
        for proc in self.procs:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            if proc.stdout:
                proc.stdout.close()
        if hasattr(self, "sb"):
            self.sb.close()

    def start_watch(self, *args):
        self.out = self.sb.tmp / f"watch-{len(self.procs)}.log"
        f = open(self.out, "w", encoding="utf-8")
        proc = subprocess.Popen([PY, str(self.sb.repo / "factory" / "bin" / "run.py"), "--watch", *args],
                                cwd=str(self.sb.repo), env=self.sb.env, stdout=f, stderr=subprocess.STDOUT)
        f.close()
        self.procs.append(proc)
        return proc

    def log(self):
        return self.out.read_text(encoding="utf-8", errors="replace")

    def wait_for(self, what, cond, timeout=120):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if cond():
                    return
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(0.3)
        self.fail(f"timed out waiting for {what}\n--- runner output ---\n{self.log() if hasattr(self, 'out') else ''}")

    def stage(self, job_id):
        return self.sb.jobjson(job_id)["stage"]

    def runs(self, job_id):
        d = self.sb.jobdir(job_id) / "runs"
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))] if d.exists() else []

    def stop_runner(self, proc, now=False):
        self.sb.script("run", "stop", *(["--now"] if now else []))
        proc.wait(timeout=60)
        return proc.returncode

    # ---------------------------------------------------------------- tests

    def test_feedback_is_picked_up_without_running_again(self):
        self.make(plan={"1": {"approve": "ESCALATE"}})
        self.sb.add_issue(1, "Status filter")
        proc = self.start_watch()
        job = "001-status-filter"
        self.wait_for("the first round to reach a human", lambda: self.stage(job) == "needs-human")
        self.assertEqual(self.sb.jobjson(job)["round"], 1)
        # only one runner per project, and status says what it does
        self.assertIn("another runner is already working", self.sb.script("run", check=False).stdout)
        self.assertIn("runner: on", self.sb.script("run", "status").stdout)
        self.assertNotIn("was updated after this runner started", self.sb.script("run", "status").stdout)
        import os  # an upgrade while it runs: the runner still has the old code, and says so
        lib = self.sb.repo / "factory" / "factorylib" / "files.py"
        os.utime(lib, (time.time() + 60, time.time() + 60))
        self.assertIn("was updated after this runner started", self.sb.script("run", "status").stdout)
        # feedback from the dashboard (or job.py) restarts the job by itself
        self.sb.job("feedback", "1", stdin="Make the filter remember its value.")
        self.wait_for("round 2 to reach a human",
                      lambda: self.sb.jobjson(job)["round"] == 2 and self.stage(job) == "needs-human")
        implementer = [r for r in self.runs(job) if r["role"] == "implementer"]
        self.assertEqual(len(implementer), 2)
        self.assertIn("The user gave feedback: read feedback-1.md", implementer[1]["task"])
        self.assertIsNone(proc.poll())                       # still watching
        self.assertEqual(self.stop_runner(proc), 0)
        self.assertIn("run: stopped (graceful)", self.log())
        self.assertIn("runner: off", self.sb.script("run", "status").stdout)

    def test_stop_now_ends_one_job_while_the_other_finishes(self):
        self.make(plan={"1": {"sleep_once": {"implementer": 90}}}, auto_merge=True, concurrency=2)
        self.sb.add_issue(1, "Slow one")
        self.sb.add_issue(2, "Quick one")
        proc = self.start_watch()
        slow, quick = "001-slow-one", "002-quick-one"
        runs = lambda: self.sb.jobdir(slow) / "runs"
        self.wait_for("the slow implementer to start", lambda: list(runs().glob("*-implementer.prompt.md")))
        t0 = time.monotonic()
        self.assertIn("paused (its running agent is stopped now)", self.sb.job("pause", "1", "--now").stdout)
        self.wait_for("the slow implementer to be ended",
                      lambda: any(r["role"] == "implementer" and r["stopped"] for r in self.runs(slow)), timeout=30)
        self.assertLess(time.monotonic() - t0, 30)             # ended, not waited out (the agent sleeps 90 s)
        self.wait_for("the quick job to merge", lambda: self.stage(quick) == "merged")
        job = self.sb.jobjson(slow)
        self.assertEqual(job["stage"], "implement")
        self.assertTrue(job["paused"]["now"])
        self.assertFalse((runs() / "stopped.md").exists())     # paused is not a failure
        rows = [l.split("\t") for l in self.sb.job("queue").stdout.splitlines()]
        self.assertIn(["hold", "1", slow, "implement", "paused; resume it in the dashboard"], rows)
        self.assertIn("implementer stopped; paused", self.log())
        # resume: the step starts over and the job finishes
        self.sb.job("unpause", "1")
        self.wait_for("the slow job to merge after resuming", lambda: self.stage(slow) == "merged")
        self.assertIsNone(self.sb.jobjson(slow)["paused"])
        self.assertEqual(self.stop_runner(proc), 0)

    def test_pause_waits_for_the_step_then_holds(self):
        self.make(plan={"1": {"sleep_once": {"spec-writer": 4}}}, auto_merge=True)
        self.sb.add_issue(1, "Thing")
        proc = self.start_watch()
        job = "001-thing"
        self.wait_for("the spec writer to start",
                      lambda: list((self.sb.jobdir(job) / "runs").glob("*-spec-writer.prompt.md")))
        self.sb.job("pause", "1")
        self.wait_for("the spec step to finish and the job to hold",
                      lambda: self.stage(job) == "implement" and "001-thing: paused" in self.log(), timeout=60)
        time.sleep(2)
        self.assertEqual(self.stage(job), "implement")        # held: no implementer ran
        self.assertFalse(any(r["role"] == "implementer" for r in self.runs(job)))
        self.sb.job("unpause", "1")
        self.wait_for("the job to merge after resuming", lambda: self.stage(job) == "merged")
        self.assertEqual(self.stop_runner(proc), 0)

    def test_stopped_job_waits_for_retry(self):
        self.make(plan={"1": {"tool_error_once": ["spec-writer"]}}, auto_merge=True)
        self.sb.add_issue(1, "Thing")
        proc = self.start_watch()
        job = "001-thing"
        stopped = self.sb.jobdir(job) / "runs" / "stopped.md"
        self.wait_for("the job to stop", stopped.exists)
        time.sleep(3)
        self.assertEqual(self.stage(job), "spec")             # not retried by itself
        self.assertEqual(sum(r["role"] == "spec-writer" for r in self.runs(job)), 1)
        self.assertIsNone(proc.poll())                        # the runner keeps going
        self.assertIn("Failed to authenticate", stopped.read_text(encoding="utf-8"))
        self.sb.job("retry", "1")
        self.wait_for("the job to merge after the retry", lambda: self.stage(job) == "merged")
        self.assertEqual(self.stop_runner(proc), 0)

    def test_one_issue_watch_ends_when_merged(self):
        self.make(auto_merge=True)
        self.sb.add_issue(1, "Thing")
        proc = self.start_watch("1")
        proc.wait(timeout=120)
        self.assertEqual(proc.returncode, 0, self.log())
        self.assertEqual(self.stage("001-thing"), "merged")

    def test_dashboard_starts_and_stops_the_runner(self):
        self.make(auto_merge=True)
        port = free_port()
        serve = subprocess.Popen([PY, str(self.sb.repo / "factory/bin/serve.py"), "--port", str(port)],
                                 cwd=str(self.sb.repo), env=self.sb.env, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True)
        self.procs.append(serve)
        token = serve.stdout.readline().strip().split("#token=", 1)[1]

        def call(path, body=None):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="POST" if body is not None else "GET",
                                         data=json.dumps(body).encode() if body is not None else None)
            req.add_header("X-Factory-Token", token)
            if body is not None:
                req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")

        self.wait_for("serve.py", lambda: call("/api/state")[0] == 200, timeout=20)
        self.assertFalse(call("/api/state")[1]["runner"]["running"])
        self.assertEqual(call("/api/runner", {"action": "stop"})[0], 409)       # nothing to stop
        self.assertEqual(call("/api/runner", {"action": "bogus"})[0], 400)
        status, data = call("/api/runner", {"action": "start"})
        self.assertEqual(status, 200, data)
        self.assertEqual(call("/api/runner", {"action": "start"})[0], 409)      # only one
        self.sb.add_issue(1, "Thing")
        self.wait_for("the dashboard's runner to merge the issue", lambda: self.stage("001-thing") == "merged")
        st = call("/api/state")[1]["runner"]
        self.assertTrue(st["running"])
        self.assertTrue(st["watch"])
        self.assertEqual(call("/api/runner", {"action": "stop"})[0], 200)
        self.wait_for("the runner to stop", lambda: not call("/api/state")[1]["runner"]["running"], timeout=60)
        status, data = call("/api/runner")
        self.assertIn("run: watching", data["log"])
        self.assertIn("run: stopped (graceful)", data["log"])


if __name__ == "__main__":
    unittest.main()
