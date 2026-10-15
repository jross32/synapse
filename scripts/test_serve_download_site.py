"""Regression tests for the public-only download-site origin."""
from __future__ import annotations

import functools
import importlib.util
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("download_server", HERE / "serve_download_site.py")
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PublicSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(module.PublicDownloads, directory=str(module.SITE))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def status(self, path, method="HEAD"):
        try:
            with urlopen(Request(self.base + path, method=method), timeout=4) as response:
                return response.status, response.headers
        except HTTPError as exc:
            return exc.code, exc.headers

    def test_public_pages(self):
        for url in ["/", "/index.html", "/features/", "/download/", "/signup/",
                    "/style.css?v=2", "/app.js", "/releases.json",
                    "/signup/signup.js", "/releases/Synapse-Premium-Setup-0.2.219-preview.exe"]:
            with self.subTest(url=url):
                status, headers = self.status(url)
                self.assertEqual(status, 200)
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_public_image(self):
        images = list((module.SITE / "assets").rglob("*.png"))
        self.assertTrue(images)
        relative = images[0].relative_to(module.SITE).as_posix()
        self.assertEqual(self.status("/" + relative)[0], 200)

    def test_private_files_and_browsing_denied(self):
        paths = ["/README.md", "/server.stderr.log", "/smoke-test.cjs",
                 "/.gitignore", "/.claude-landing-brief.txt", "/artifacts/",
                 "/assets/", "/assets/reference/", "/../README.md",
                 "/%2e%2e/README.md", "/assets/%2e%2e/README.md",
                 "/assets/reference/website-asset-pack/"]
        for path in paths:
            for method in ("HEAD", "GET"):
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.status(path, method)[0], 404)


if __name__ == "__main__":
    unittest.main()
