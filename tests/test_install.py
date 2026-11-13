"""install.py: profiles into AGENTS.md / CLAUDE.md, and refreshing prompts on upgrade."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from sandbox import PACKAGE, PY

PROFILES = sorted(p.stem for p in (PACKAGE / "profiles").glob("*.md") if p.stem != "README")
SUBSECTIONS = ["### What this project is", "### Users and roles", "### Sensitive areas", "### Authorization",
               "### Data rules", "### UI conventions", "### Verify", "### Terms"]


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="af-install-"))
        self.repo = self.tmp / "my app"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def install(self, *args, check=True):
        r = subprocess.run([PY, str(PACKAGE / "install.py"), str(self.repo), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if check and r.returncode != 0:
            raise AssertionError(r.stdout + r.stderr)
        return r

    def read(self, rel):
        return (self.repo / rel).read_text(encoding="utf-8")

    def test_profiles_have_every_subsection_in_order(self):
        self.assertEqual(PROFILES, ["api-service", "backoffice", "blank", "data-pipeline", "library", "mobile-app", "web-app"])
        for name in PROFILES:
            text = (PACKAGE / "profiles" / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn("## Factory profile", text, name)
            at = [text.index(s) for s in SUBSECTIONS]
            self.assertEqual(at, sorted(at), name)
            self.assertLess(len(text.splitlines()), 50, f"{name} is read on every job: keep it short")

    def test_profile_goes_into_agents_md_and_claude_imports_it(self):
        (self.repo / "AGENTS.md").write_text("# My app\n\nRun tests with make test.\n", encoding="utf-8")
        out = self.install("--profile", "api-service").stdout
        agents = self.read("AGENTS.md")
        self.assertTrue(agents.startswith("# My app\n\nRun tests with make test.\n"))  # kept as it was
        self.assertIn("## Factory profile", agents)
        self.assertNotIn("<!--", agents)  # the profile's hint comment isn't copied
        self.assertEqual(self.read("CLAUDE.md").strip(), "@AGENTS.md")
        self.assertIn("added the 'api-service' Factory profile", out)
        # running again changes nothing and never adds a second profile
        out = self.install("--upgrade", "--profile", "web-app").stdout
        self.assertEqual(self.read("AGENTS.md").count("## Factory profile"), 1)
        self.assertEqual(self.read("CLAUDE.md").count("@AGENTS.md"), 1)
        self.assertIn("already has a Factory profile", out)

    def test_existing_claude_md_gets_one_import_line(self):
        (self.repo / "CLAUDE.md").write_text("# Notes\nUse pnpm.", encoding="utf-8")
        self.install("--profile", "blank")
        self.assertEqual(self.read("CLAUDE.md"), "# Notes\nUse pnpm.\n\n@AGENTS.md\n")

    def test_install_without_profile_suggests_one(self):
        out = self.install().stdout
        self.assertIn("No Factory profile yet", out)
        self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_upgrade_keeps_prompts_unless_asked(self):
        self.install()
        intake = self.repo / ".claude" / "agents" / "intake.md"
        intake.write_text("my tailored intake\n", encoding="utf-8")
        out = self.install("--upgrade").stdout
        self.assertEqual(intake.read_text(encoding="utf-8"), "my tailored intake\n")
        self.assertIn("add --prompts", out)
        out = self.install("--upgrade", "--prompts").stdout
        self.assertNotEqual(intake.read_text(encoding="utf-8"), "my tailored intake\n")
        saved = list((self.repo / "factory" / "archive").glob("prompts-*/.claude/agents/intake.md"))
        self.assertEqual([p.read_text(encoding="utf-8") for p in saved], ["my tailored intake\n"])
        self.assertIn("previous prompts (1 files) are saved", out)

    def test_bad_options(self):
        self.assertIn("no profile 'nope'", self.install("--profile", "nope", check=False).stderr)
        self.assertIn("--prompts only goes with --upgrade", self.install("--prompts", check=False).stderr)


if __name__ == "__main__":
    unittest.main()
