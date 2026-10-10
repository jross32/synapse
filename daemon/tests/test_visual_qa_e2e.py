"""End-to-end proof of isolated Visual QA scenarios, interactions and screenshots."""
import json
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        html = b"""<!doctype html><html><head><title>Visual QA Fixture</title>
<style>body{background:#141928;color:#f2ecff;font:16px Arial;margin:16px}
button,input{font:inherit}</style></head><body>
<h1>Visual QA Fixture</h1><input id='name'><input id='upload' type='file'>
<button id='go'>Update</button><output id='status'>Ready</output>
<script>document.querySelector('#go').onclick=()=>{
 document.querySelector('#status').textContent='Hello '+document.querySelector('#name').value;
};</script></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, *_):
        pass


def test_visual_qa_e2e_click_form_upload_and_reference():
    assert NODE
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            (temp / "tiny.txt").write_text("Test fixture, not real clothing.", encoding="utf-8")
            manifest = {
                "baseUrl": f"http://127.0.0.1:{server.server_port}",
                "authorizedTestEnvironment": True,
                "scenarios": [{
                    "name": "fixture interactions",
                    "path": "/",
                    "allowInteractions": True,
                    "viewport": {"width": 390, "height": 844},
                    "steps": [
                        {"action": "expectText", "selector": "h1", "text": "Visual QA Fixture"},
                        {"action": "fill", "selector": "#name", "value": "Synapse"},
                        {"action": "expectValue", "selector": "#name", "value": "Synapse"},
                        {"action": "upload", "selector": "#upload", "file": "tiny.txt"},
                        {"action": "click", "selector": "#go"},
                        {"action": "expectText", "selector": "#status", "text": "Hello Synapse"},
                    ],
                }],
            }
            spec = temp / "manifest.json"
            spec.write_text(json.dumps(manifest), encoding="utf-8")

            def run(folder):
                call = subprocess.run(
                    [NODE, str(ROOT / "scripts" / "visual-qa-suite.mjs"), str(spec), str(temp / folder)],
                    cwd=ROOT, capture_output=True, text=True, timeout=80,
                )
                report = temp / folder / "report.json"
                assert report.exists(), f"No report: {call.stdout} {call.stderr}"
                data = json.loads(report.read_text(encoding="utf-8"))
                assert call.returncode == 0, f"{call.stdout}\n{call.stderr}\n{data}"
                assert data["counts"]["passed"] == 1, data
                return data

            first = run("first")
            case = first["scenarios"][0]
            assert len(case["steps"]) == 6
            assert case["metrics"]["scrollWidth"] <= case["metrics"]["viewport"]
            png = temp / "first" / "scenario-01" / case["screenshot"]
            assert png.is_file()

            # Use the exact captured image as a deterministic approved fixture baseline.
            baseline = temp / "approved-baseline.png"
            shutil.copyfile(png, baseline)
            manifest["scenarios"][0]["baseline"] = "approved-baseline.png"
            manifest["scenarios"][0]["requireVisualMatch"] = True
            spec.write_text(json.dumps(manifest), encoding="utf-8")
            second = run("with-baseline")
            assert second["scenarios"][0]["reference"]["status"] == "PASS"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    test_visual_qa_e2e_click_form_upload_and_reference()
    print("VISUAL QA E2E PASS")
