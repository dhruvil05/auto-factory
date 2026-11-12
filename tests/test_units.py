"""Unit tests for config validation, local-env checks, routing and cost."""

import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
FACTORY = PACKAGE / "template" / "factory"
sys.path.insert(0, str(FACTORY))

from factorylib import config, localenv  # noqa: E402

spec = importlib.util.spec_from_file_location("route", FACTORY / "bin" / "route.py")
route = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route)


def cfg(**changes):
    c = copy.deepcopy(config.DEFAULTS)
    c["checks"] = [{"name": "tests", "cmd": "run tests", "enabled": True, "timeout": 60, "retry_on_fail": 0}]
    c.update(changes)
    return c


class ConfigTest(unittest.TestCase):
    def test_template_config_is_valid(self):
        raw = json.loads((FACTORY / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config.validate(config._merge(config.DEFAULTS, raw)), [])
        self.assertEqual(raw, config.DEFAULTS)

    def test_rejects_rewriting_flags(self):
        for cmd in ("eslint . --fix", "prettier --write .", "jest -u", "vitest --update-snapshots"):
            c = cfg(checks=[{"name": "lint", "cmd": cmd, "enabled": True, "timeout": 60, "retry_on_fail": 0}])
            self.assertTrue(any("rewrites files" in e for e in config.validate(c)), cmd)
        ok = cfg(checks=[{"name": "lint", "cmd": "php -l app/x.php --no-fix-me", "enabled": True,
                          "timeout": 60, "retry_on_fail": 0}])
        self.assertEqual(config.validate(ok), [])

    def test_locked_protected_paths(self):
        c = cfg(protected_paths=[".github/workflows/*"])
        errors = config.validate(c)
        self.assertIn("protected_paths must keep factory/*", errors)
        self.assertIn("protected_paths must keep .claude/*", errors)

    def test_high_risk_never_auto_merges(self):
        c = cfg()
        c["routing"]["high"]["auto_merge"] = True
        self.assertTrue(any("high-risk" in e for e in config.validate(c)))

    def test_misc_errors(self):
        c = cfg(concurrency=9, shell="zsh")
        c["models"]["intake"] = "gpt"
        c["checks"].append(dict(c["checks"][0]))
        c["env"]["dev_server"] = "php artisan serve"
        c["cost_caps_usd"]["job"] = -1
        errors = " | ".join(config.validate(c))
        for needle in ("concurrency", "shell", "models.intake", "used twice", "{PORT}", "cost_caps_usd.job"):
            self.assertIn(needle, errors)

    def test_save_keeps_history(self):
        with tempfile.TemporaryDirectory() as d:
            path, hist = Path(d) / "config.json", Path(d) / "hist"
            config.save(cfg(), path, hist)
            config.save(cfg(concurrency=2), path, hist)
            self.assertEqual(json.loads(path.read_text())["concurrency"], 2)
            self.assertEqual(len(list(hist.glob("*.json"))), 1)
            with self.assertRaises(config.ConfigError):
                config.save(cfg(concurrency=0), path, hist)
            self.assertEqual(json.loads(path.read_text())["concurrency"], 2)

    def test_removed_entries_stay_removed(self):
        with tempfile.TemporaryDirectory() as d:
            path, hist = Path(d) / "config.json", Path(d) / "hist"
            c = cfg()
            del c["runner"]["harnesses"]["codex"]
            c["runner"]["harnesses"]["claude"]["models"].pop("haiku")
            del c["surface_reviewers"]["ui"]["ui"]
            config.save(c, path, hist)
            loaded = config.load(path)
            self.assertNotIn("codex", loaded["runner"]["harnesses"])
            self.assertNotIn("haiku", loaded["runner"]["harnesses"]["claude"]["models"])
            self.assertEqual(loaded["surface_reviewers"]["ui"], {"ux": "sonnet"})
            self.assertEqual(loaded["runner"]["agent_timeout_minutes"], 60)  # other keys still filled

    def test_runner_validation(self):
        c = cfg()
        c["runner"]["harness"] = "nope"
        c["runner"]["role_harness"] = {"reviewer-magic": "claude", "intake": "ghost"}
        c["runner"]["harnesses"]["codex"]["cmd"] = "codex exec"  # file prompt without {PROMPT_FILE}
        c["runner"]["harnesses"]["claude"]["models"]["opus"] = ""
        errors = " | ".join(config.validate(c))
        for needle in ("runner.harness must be one of", "unknown role 'reviewer-magic'",
                       "unknown agent tool 'ghost'", "{PROMPT_FILE}", "claude.models"):
            self.assertIn(needle, errors)

    def test_load_fills_missing_keys(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps({"concurrency": 2, "env": {"migrate": "m"}}))
            c = config.load(path)
            self.assertEqual(c["concurrency"], 2)
            self.assertEqual(c["env"]["migrate"], "m")
            self.assertEqual(c["env"]["local_hosts"], ["localhost", "127.0.0.1", "::1"])


class LocalEnvTest(unittest.TestCase):
    def test_foreign_hosts(self):
        values = localenv.parse_env(
            "DB_HOST=127.0.0.1\nREDIS_URL=redis://localhost:6379\nAPP_URL=http://app.test\n"
            "MAIL_HOST=smtp.mailgun.org\nAPI=https://api.stripe.com/v1\n# c\nexport X_SERVER=db.local.localhost\n")
        bad = localenv.foreign_hosts(values, ["localhost", "127.0.0.1", "::1"])
        self.assertEqual(sorted(bad), [("API", "api.stripe.com"), ("MAIL_HOST", "smtp.mailgun.org")])

    def test_ipv6_and_ports(self):
        self.assertTrue(localenv.is_local("[::1]", ["::1"]))
        bad = localenv.foreign_hosts({"DB_HOST": "10.0.0.5:3306"}, ["localhost"])
        self.assertEqual(bad, [("DB_HOST", "10.0.0.5")])


class RouteTest(unittest.TestCase):
    def test_low_no_surfaces(self):
        c = cfg()
        c["routing"]["low"]["auto_merge"] = True
        reviewers, auto, reason, human = route.plan(c, {"risk": "low", "surfaces": []})
        self.assertEqual((reviewers, auto, reason, human), ({"code": "haiku"}, True, None, False))

    def test_surfaces_add_reviewers_and_force_human(self):
        c = cfg()
        c["routing"]["medium"]["auto_merge"] = True
        reviewers, auto, reason, human = route.plan(c, {"risk": "medium", "surfaces": ["ui", "data"]})
        self.assertEqual(reviewers, {"code": "sonnet", "ux": "sonnet", "ui": "haiku", "data": "opus"})
        self.assertFalse(auto)
        self.assertEqual(reason, "data changes always go to a human")
        self.assertTrue(human)

    def test_high_risk(self):
        _, auto, reason, _ = route.plan(cfg(), {"risk": "high", "surfaces": []})
        self.assertEqual((auto, reason), (False, "high risk always goes to a human"))

    def test_unknown_values(self):
        with self.assertRaises(ValueError):
            route.plan(cfg(), {"risk": "huge", "surfaces": []})
        with self.assertRaises(ValueError):
            route.plan(cfg(), {"risk": "low", "surfaces": ["blockchain"]})


class CostTest(unittest.TestCase):
    def test_cost_by_agent_and_partial(self):
        from factorylib import cost, paths
        with tempfile.TemporaryDirectory() as d:
            os.environ["CLAUDE_CONFIG_DIR"] = d
            try:
                sub = Path(cost.transcripts_dir()) / "session1" / "subagents"
                sub.mkdir(parents=True)
                first = {"type": "user", "message": {"role": "user", "content": "Job: 007-x. Job folder: /r/factory/jobs/007-x/."}}
                msg = {"type": "assistant", "message": {"id": "m1", "model": "claude-opus-5-5", "usage": {
                    "input_tokens": 1_000_000, "output_tokens": 0, "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0}}}
                other = {"type": "assistant", "message": {"id": "m2", "model": "claude-unknown", "usage": {
                    "input_tokens": 5, "output_tokens": 5}}}
                (sub / "agent-a.jsonl").write_text("\n".join(json.dumps(x) for x in (first, msg, msg, other)) + "\n")
                (sub / "agent-a.meta.json").write_text(json.dumps({"agentType": "implementer"}))
                (sub / "agent-b.jsonl").write_text(json.dumps({"type": "user", "message": {"content": "Job: 008-y."}}) + "\n")
                prices = {"claude-opus-5-5": {"input": 2.0, "output": 10.0, "cache_write_5m": 2.5,
                                              "cache_write_1h": 4.0, "cache_read": 0.2}}
                result = cost.job_cost("007-x", prices)
                self.assertEqual(result, {"usd": 2.0, "by_agent": {"implementer": 2.0}, "partial": True})
                self.assertEqual(cost.job_cost("009-none", prices)["usd"], 0.0)
                slug = "".join(ch if ch.isalnum() else "-" for ch in str(paths.REPO))
                self.assertEqual(cost.transcripts_dir(), Path(d) / "projects" / slug)
            finally:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)


if __name__ == "__main__":
    unittest.main()
