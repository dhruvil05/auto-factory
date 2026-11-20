"""put.py, the file helper for agent tools without a working editor, and the harness's
token savers: job files in the prompt, safe fences and ripgrep on PATH."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
FACTORY = PACKAGE / "template" / "factory"
PUT = FACTORY / "bin" / "put.py"
sys.path.insert(0, str(FACTORY))

from factorylib import harness  # noqa: E402


class PutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, *args, text=""):
        return subprocess.run([sys.executable, str(PUT), *args], input=text.encode("utf-8"),
                              capture_output=True, cwd=self.d)

    def test_write_creates_folders_and_keeps_crlf(self):
        r = self.put("write", str(self.d / "a" / "b.md"), text="hello — world\nsecond")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.d / "a" / "b.md").read_bytes().decode("utf-8"), "hello — world\nsecond\n")
        (self.d / "w.txt").write_bytes(b"old\r\n")
        self.put("write", "w.txt", text="one\ntwo\n")
        self.assertEqual((self.d / "w.txt").read_bytes(), b"one\r\ntwo\r\n")

    def test_patch_add_update_delete(self):
        (self.d / "x.py").write_bytes(b"def a():\r\n    return 1\r\n\r\ndef b():\r\n    return 1\r\n")
        (self.d / "gone.txt").write_text("bye\n")
        patch = ("*** Begin Patch\n*** Add File: new/n.md\n+# Title\n+\n+text\n"
                 "*** Update File: x.py\n@@ def b():\n-    return 1\n+    return 2\n"
                 "*** Delete File: gone.txt\n*** End Patch\n")
        r = self.put("patch", text=patch)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"updated x.py", r.stdout)
        self.assertEqual((self.d / "x.py").read_bytes(), b"def a():\r\n    return 1\r\n\r\ndef b():\r\n    return 2\r\n")
        self.assertEqual((self.d / "new" / "n.md").read_text(), "# Title\n\ntext\n")
        self.assertFalse((self.d / "gone.txt").exists())

    def test_context_lines_and_trailing_spaces(self):
        (self.d / "c.css").write_text(".a {\n  color: red;  \n}\n.b {\n  color: red;\n}\n")
        patch = "*** Begin Patch\n*** Update File: c.css\n .b {\n-  color: red;\n+  color: blue;\n }\n*** End Patch"
        self.assertEqual(self.put("patch", text=patch).returncode, 0)
        self.assertEqual((self.d / "c.css").read_text(), ".a {\n  color: red;  \n}\n.b {\n  color: blue;\n}\n")
        patch = "*** Begin Patch\n*** Update File: c.css\n-  color: red;\n+  color: green;\n*** End Patch"
        self.assertEqual(self.put("patch", text=patch).returncode, 0)   # matches once, ignoring trailing spaces
        self.assertIn("color: green;", (self.d / "c.css").read_text())

    def test_bad_patches_write_nothing(self):
        (self.d / "t.txt").write_text("same\nother\nsame\n")
        before = (self.d / "t.txt").read_text()
        cases = {
            "match 2 places": "*** Begin Patch\n*** Add File: ok.txt\n+x\n*** Update File: t.txt\n-same\n+new\n*** End Patch",
            "aren't in the file": "*** Begin Patch\n*** Update File: t.txt\n-missing\n+new\n*** End Patch",
            "must end with": "*** Begin Patch\n*** Update File: t.txt\n-same\n+new\n",
            "no such file to update": "*** Begin Patch\n*** Update File: nope.txt\n-a\n+b\n*** End Patch",
            "must start with '+'": "*** Begin Patch\n*** Add File: n.txt\nplain\n*** End Patch",
        }
        for why, patch in cases.items():
            r = self.put("patch", text=patch)
            self.assertEqual(r.returncode, 1, why)
            self.assertIn(why, r.stderr.decode(), why)
        self.assertEqual((self.d / "t.txt").read_text(), before)
        self.assertFalse((self.d / "ok.txt").exists())   # checked everything before writing anything

    def test_usage(self):
        self.assertEqual(self.put().returncode, 2)


class PromptSaverTest(unittest.TestCase):
    def test_fence_is_longer_than_any_backticks_inside(self):
        self.assertEqual(harness.fence("plain"), "```")
        self.assertEqual(harness.fence("a ```py\nx\n``` b"), "````")

    def test_preamble_is_stable_and_names_the_helper(self):
        self.assertEqual(harness.preamble(), harness.preamble())
        self.assertIn("put.py\" write", harness.preamble())
        self.assertEqual("PowerShell" in harness.preamble(), os.name == "nt")
        self.assertNotIn("{", harness.preamble().split("apply_patch-style")[0])

    def test_tool_path_adds_a_bundled_ripgrep(self):
        with tempfile.TemporaryDirectory() as home:
            exe = "rg.exe" if os.name == "nt" else "rg"
            rg = Path(home) / ".codex" / "packages" / "standalone" / "releases" / "1.0" / "codex-path" / exe
            rg.parent.mkdir(parents=True)
            rg.write_bytes(b"")
            rg.chmod(0o755)
            empty = Path(home) / "empty"
            empty.mkdir()
            old = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE")}
            os.environ["HOME"] = os.environ["USERPROFILE"] = home
            try:
                self.assertEqual(harness.tool_path(str(empty)), str(rg.parent) + os.pathsep + str(empty))
                self.assertIsNone(harness.tool_path(str(rg.parent)))          # already on PATH
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
