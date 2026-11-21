"""The dashboard server: auth, host check, settings saves, file access."""

import json
import socket
import subprocess
import time
import unittest
import urllib.error
import urllib.request

from sandbox import PY, Sandbox


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox()
        cls.sb.add_issue(1, "Add a status filter to orders")
        cls.job_id = cls.sb.job("create", "1").stdout.strip()
        cls.sb.intake(cls.job_id)
        cls.port = free_port()
        cls.proc = subprocess.Popen([PY, str(cls.sb.repo / "factory/bin/serve.py"), "--port", str(cls.port)],
                                    cwd=str(cls.sb.repo), env=cls.sb.env, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True)
        line = cls.proc.stdout.readline()
        cls.token = line.strip().split("#token=", 1)[1]
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", cls.port), 0.2).close()
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.proc.kill()
        cls.proc.wait()
        cls.sb.close()

    def call(self, path, body=None, token=True, host=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     method="POST" if body is not None else "GET")
        if token:
            req.add_header("X-Factory-Token", self.token if token is True else token)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return r.status, json.loads(raw) if r.headers.get_content_type() == "application/json" else raw
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_token_required(self):
        self.assertEqual(self.call("/api/state", token=False)[0], 401)
        self.assertEqual(self.call("/api/state", token="nope")[0], 401)

    def test_host_checked(self):
        self.assertEqual(self.call("/api/state", host="evil.example:80")[0], 403)

    def test_state(self):
        status, data = self.call("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(data["project"]["name"], "proj app")
        self.assertEqual([j["id"] for j in data["jobs"]], [self.job_id])
        self.assertEqual(data["slots"], {"used": 1, "total": 1})
        self.assertFalse(data["paused"])

    def test_job_files_and_traversal(self):
        status, data = self.call(f"/api/jobs/{self.job_id}")
        self.assertEqual(status, 200)
        intake = next(f for f in data["files"] if f["path"] == "intake.md")
        self.assertEqual(intake["first_line"], "DECISION: ACCEPT")
        self.assertEqual(intake["summary"], ["Clear request"])
        status, data = self.call(f"/api/jobs/{self.job_id}/file?path=intake.md")
        self.assertIn("RISK: low", data["content"])
        self.assertEqual(self.call(f"/api/jobs/{self.job_id}/file?path=../../config.json")[0], 404)
        self.assertEqual(self.call("/api/jobs/..%2F..%2Fx")[0], 404)

    def test_config_save_validates_and_keeps_history(self):
        _, data = self.call("/api/state")
        cfg = data["config"]
        bad = json.loads(json.dumps(cfg))
        bad["checks"][0]["cmd"] = "eslint . --fix"
        status, out = self.call("/api/config", {"config": bad})
        self.assertEqual(status, 400)
        self.assertTrue(any("rewrites files" in e for e in out["errors"]))
        good = json.loads(json.dumps(cfg))
        good["max_rounds"] = 4
        status, out = self.call("/api/config", {"config": good})
        self.assertEqual(status, 200)
        self.assertEqual(self.sb.config()["max_rounds"], 4)
        self.assertTrue(self.call("/api/state")[1]["config_dirty"])
        self.assertGreaterEqual(len(self.call("/api/config/history")[1]["entries"]), 1)
        self.assertIn('"max_rounds": 4', self.call("/api/config/diff")[1]["diff"])

    def test_pause(self):
        self.assertEqual(self.call("/api/pause", {"paused": True})[1], {"paused": True})
        self.assertTrue((self.sb.repo / "factory/PAUSE").exists())
        self.assertEqual(self.call("/api/pause", {"paused": False})[1], {"paused": False})

    def test_preflight(self):
        # the page posts with no body at all; that must work too
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/preflight", data=b"", method="POST")
        req.add_header("X-Factory-Token", self.token)
        with urllib.request.urlopen(req, timeout=60) as r:
            self.assertEqual(r.status, 202)
        for _ in range(120):
            data = self.call("/api/preflight")[1]
            if data["status"] == "done":
                break
            time.sleep(0.5)
        self.assertEqual(data["result"]["gate"], "PASS", data)

    def test_feedback_refused_when_not_waiting(self):
        status, out = self.call(f"/api/jobs/{self.job_id}/feedback", {"text": "do it differently"})
        self.assertEqual(status, 409)
        self.assertIn("not needs-human", out["error"])

    def test_job_control(self):
        status, out = self.call(f"/api/jobs/{self.job_id}/control", {"action": "pause"})
        self.assertEqual(status, 200, out)
        self.assertFalse(out["job"]["paused"]["now"])
        self.assertEqual(self.call("/api/state")[1]["slots"]["used"], 0)   # a paused job holds no slot
        status, out = self.call(f"/api/jobs/{self.job_id}/control", {"action": "resume"})
        self.assertEqual(status, 200, out)
        self.assertIsNone(out["job"]["paused"])
        self.assertEqual(self.call(f"/api/jobs/{self.job_id}/control", {"action": "retry"})[0], 409)  # nothing stopped
        self.assertEqual(self.call(f"/api/jobs/{self.job_id}/control", {"action": "explode"})[0], 400)
        stopped = self.sb.jobdir(self.job_id) / "runs" / "stopped.md"
        stopped.parent.mkdir(parents=True, exist_ok=True)
        stopped.write_text("STOPPED\nWHEN: 2026-11-12T10:00:00Z\n\nintake (claude) failed: not signed in\n", encoding="utf-8")
        job = next(j for j in self.call("/api/state")[1]["jobs"] if j["id"] == self.job_id)
        self.assertEqual(job["stopped"], "intake (claude) failed: not signed in")
        self.assertEqual(self.call(f"/api/jobs/{self.job_id}/control", {"action": "retry"})[0], 200)
        self.assertFalse(stopped.exists())

    def test_runner_status_and_issue_images(self):
        status, data = self.call("/api/runner")
        self.assertEqual(status, 200)
        self.assertFalse(data["runner"]["running"])
        self.assertFalse(self.call("/api/state")[1]["runner"]["running"])
        # an upgrade while serve.py runs: the page says to restart it (its Python is the old code)
        self.assertFalse(self.call("/api/state")[1]["server_outdated"])
        import os
        import time
        lib = self.sb.repo / "factory" / "factorylib" / "files.py"
        before = lib.stat()
        os.utime(lib, (time.time() + 60, time.time() + 60))
        try:
            self.assertTrue(self.call("/api/state")[1]["server_outdated"])
        finally:
            os.utime(lib, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertFalse(self.call("/api/state")[1]["server_outdated"])
        img = self.sb.jobdir(self.job_id) / "attachments" / "image-1.jpg"
        img.parent.mkdir(parents=True, exist_ok=True)
        img.write_bytes(b"\xff\xd8\xff\xe0fake jpeg")
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/jobs/{self.job_id}/file?path=attachments/image-1.jpg")
        req.add_header("X-Factory-Token", self.token)
        with urllib.request.urlopen(req, timeout=30) as r:
            self.assertEqual(r.headers.get_content_type(), "image/jpeg")
            self.assertEqual(r.read(), b"\xff\xd8\xff\xe0fake jpeg")

    def test_dashboard_page(self):
        status, body = self.call("/")
        if (self.sb.repo / "factory/dashboard/index.html").exists():
            self.assertEqual(status, 200)
            self.assertIn(b"<html", body.lower())


if __name__ == "__main__":
    unittest.main()
