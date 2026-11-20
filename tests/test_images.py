"""Images in issues: found, downloaded (only from allowed hosts, only real images), and pointed at from issue.md."""

import http.server
import sys
import threading
import unittest

from sandbox import HERE, Sandbox

sys.path.insert(0, str(HERE.parent / "template" / "factory"))
from factorylib import attachments  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 32
UUID = "0f3c2a1e-1111-4222-8333-444455556666"


class Images(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/b.gif")
            self.end_headers()
            return
        body, ctype = {"/a.png": (PNG, "image/png"), "/b.gif": (GIF, "image/gif"),
                       f"/signed/{UUID}.png": (PNG, "image/png"),
                       "/page.html": (b"<html>not an image</html>", "image/png")}.get(self.path, (None, None))
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class UnitTest(unittest.TestCase):
    def test_links_found_in_markdown_and_html(self):
        text = ('See ![the form](https://github.com/user-attachments/assets/abc) and\n'
                '<img width="300" alt="x" src="https://private-user-images.githubusercontent.com/1/2.png?jwt=a&amp;b=1">')
        urls = [u for _, _, u in attachments.image_links(text)]
        self.assertEqual(urls, ["https://github.com/user-attachments/assets/abc",
                                "https://private-user-images.githubusercontent.com/1/2.png?jwt=a&b=1"])

    def test_only_github_hosts_over_https(self):
        self.assertTrue(attachments.allowed("https://github.com/user-attachments/assets/x"))
        self.assertTrue(attachments.allowed("https://user-images.githubusercontent.com/1/x.png"))
        self.assertFalse(attachments.allowed("http://github.com/x.png"))
        self.assertFalse(attachments.allowed("https://github.com.evil.example/x.png"))
        self.assertFalse(attachments.allowed("https://evil.example/x.png"))
        self.assertFalse(attachments.allowed("file:///etc/passwd"))

    def test_kind_is_checked_by_content(self):
        self.assertEqual(attachments.kind_of(PNG), "png")
        self.assertEqual(attachments.kind_of(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "webp")
        self.assertIsNone(attachments.kind_of(b"<svg onload=alert(1)>"))

    def test_rewrite(self):
        saved = {"https://github.com/a": ("image-1.png", "1 KB"), "https://github.com/b": (None, "couldn't download: HTTP 404")}
        out = attachments.rewrite("x ![form](https://github.com/a) y ![](https://github.com/b)", saved, "attachments/")
        self.assertEqual(out, "x [image (form): attachments/image-1.png] y [image: https://github.com/b — couldn't download: HTTP 404]")

    def test_signed_links_by_asset_id(self):
        html = f'<p><a href="x"><img src="https://private-user-images.githubusercontent.com/9/1-{UUID}.png?jwt=t" alt="s"></a></p>'
        self.assertEqual(attachments.signed_links(html),
                         {UUID: f"https://private-user-images.githubusercontent.com/9/1-{UUID}.png?jwt=t"})


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Images)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.sb = Sandbox()
        self.sb.env["FACTORY_IMAGE_HOSTS"] = f"127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.sb.close()

    def test_issue_images_saved_and_linked(self):
        b = self.base
        body = (f"The form is cramped:\n\n![the form]({b}/a.png)\n\n<img src=\"{b}/redirect\">\n\n"
                f"![elsewhere](https://evil.example/x.png)\n![fake]({b}/page.html)\n![gone]({b}/missing.png)\n"
                f"![private](https://github.com/user-attachments/assets/{UUID})")
        self.sb.add_issue(1, "Fix the form", body=body)
        s = self.sb.gh()
        s["issues"]["1"]["body_html"] = f'<img src="{b}/signed/{UUID}.png" alt="private">'
        s["issues"]["1"]["comments"].append({"author": {"login": "ops-lead"}, "createdAt": "2026-11-12T10:00:00Z",
                                             "body": f"Also this: ![second]({b}/a.png)", "body_html": ""})
        s["issues"]["1"]["comments"].append({"author": {"login": "stranger"}, "createdAt": "2026-11-12T10:01:00Z",
                                             "body": f"![spam]({b}/b.gif)", "body_html": ""})
        self.sb.put_gh(s)
        job_id = self.sb.job("create", "1").stdout.strip()
        d = self.sb.jobdir(job_id)
        files = sorted(p.name for p in (d / "attachments").iterdir())
        self.assertEqual(files, ["image-1.png", "image-2.gif", "image-3.png"])  # a.png once, redirect, signed
        self.assertEqual((d / "attachments" / "image-2.gif").read_bytes(), GIF)
        md = (d / "issue.md").read_text(encoding="utf-8")
        self.assertIn("> [image (the form): attachments/image-1.png]", md)
        self.assertIn("> [image: attachments/image-2.gif]", md)
        self.assertIn("> [image (private): attachments/image-3.png]", md)    # through GitHub's signed link
        self.assertIn("> Also this: [image (second): attachments/image-1.png]", md)
        self.assertIn("not a GitHub image link", md)
        self.assertIn("not a PNG, JPEG, GIF or WebP image", md)
        self.assertIn("HTTP 404", md)
        self.assertNotIn("spam", md)                                       # untrusted commenters stay out
        images = md.split("## Images", 1)[1]
        self.assertIn(f"{(d / 'attachments' / 'image-1.png').as_posix()}", images)
        self.assertIn("3 image links couldn't be saved", images)

    def test_no_images_no_section(self):
        self.sb.add_issue(1, "Plain", body="Just words.")
        job_id = self.sb.job("create", "1").stdout.strip()
        self.assertNotIn("## Images", (self.sb.jobdir(job_id) / "issue.md").read_text(encoding="utf-8"))
        self.assertFalse((self.sb.jobdir(job_id) / "attachments").exists())
        self.assertFalse(any(c[0] == "api" and c[1] != "user" for c in self.sb.gh()["calls"]))


if __name__ == "__main__":
    unittest.main()
