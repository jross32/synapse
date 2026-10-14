"""Public-only file server and URL traversal regression."""
import functools
import importlib.util
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("serve_download_site", ROOT/"scripts"/"serve_download_site.py")
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)


def test_site_root_responds_without_exposing_daemon_secret():
    handler = functools.partial(site.PublicDownloads, directory=str(site.SITE))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=3) as r:
            data = r.read(20000)
            assert r.status == 200
            assert b"<html" in data.lower() or b"<!doctype html" in data.lower()
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/../data/auth-token", timeout=3)
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError("Download site exposed a file outside public root")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
