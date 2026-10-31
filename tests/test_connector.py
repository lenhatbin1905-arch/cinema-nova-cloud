import json
import shutil
import subprocess
import threading
import unittest
from http.client import HTTPConnection
from tempfile import TemporaryDirectory
from pathlib import Path

import connector


class ConnectorHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.old = (connector.PORT, connector.ALLOWED_ORIGINS, connector.PAIR_TOKEN, connector.DATA_ROOT)
        connector.PORT = 18765
        connector.ALLOWED_ORIGINS = {"https://cinemanova-e8rx.onrender.com", "http://127.0.0.1:18765", "http://localhost:18765"}
        connector.PAIR_TOKEN = "test-pairing-token-do-not-use"
        connector.DATA_ROOT = Path(cls.temp.name)
        connector.DB_FILE = Path(cls.temp.name) / "test.sqlite3"
        cls.server = connector.ConnectorServer(("127.0.0.1", connector.PORT), connector.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        connector.PORT, connector.ALLOWED_ORIGINS, connector.PAIR_TOKEN, connector.DATA_ROOT = cls.old
        cls.temp.cleanup()

    def request(self, method, path, token=None, origin="https://cinemanova-e8rx.onrender.com", body=None):
        conn = HTTPConnection("127.0.0.1", 18765, timeout=3)
        headers = {"Origin": origin}
        if token:
            headers["X-CinemaNova-Token"] = token
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(payload))
        conn.request(method, path, payload, headers)
        response = conn.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        conn.close()
        return result

    def test_health_reports_loopback_and_no_fake_production(self):
        status, raw, headers = self.request("GET", "/api/health")
        data = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(data["bound_to"], "127.0.0.1")
        self.assertFalse(data["providers"]["mock"]["generation_enabled"])
        self.assertEqual(headers["Access-Control-Allow-Origin"], "https://cinemanova-e8rx.onrender.com")

    def test_local_page_includes_external_connector_script(self):
        status, raw, headers = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b'src="cloud-connector.js"', raw)
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        status, raw, headers = self.request("GET", "/cloud-connector.js")
        self.assertEqual(status, 200)
        self.assertIn(b"cinema-nova-pairing-token", raw)
        self.assertTrue(headers["Content-Type"].startswith("text/javascript"))

    def test_static_publish_output_contains_every_page_asset(self):
        with TemporaryDirectory() as output:
            publish = Path(output) / "public"
            publish.mkdir()
            shutil.copy("index.html", publish / "index.html")
            shutil.copy("cloud-connector.js", publish / "cloud-connector.js")
            self.assertIn('src="cloud-connector.js"', (publish / "index.html").read_text(encoding="utf-8"))
            self.assertTrue((publish / "cloud-connector.js").is_file())

    def test_rejects_untrusted_origin(self):
        status, raw, _ = self.request("GET", "/api/health", origin="https://evil.example")
        self.assertEqual(status, 403)
        self.assertIn("Origin", json.loads(raw)["error"])

    def test_private_network_preflight_is_scoped_and_supported(self):
        status, _, headers = self.request("OPTIONS", "/api/providers")
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Private-Network"], "true")
        self.assertEqual(headers["Access-Control-Allow-Origin"], "https://cinemanova-e8rx.onrender.com")
        status, _, _ = self.request("OPTIONS", "/api/providers", origin="https://evil.example")
        self.assertEqual(status, 403)

    def test_provider_status_requires_pairing(self):
        status, _, _ = self.request("GET", "/api/providers")
        self.assertEqual(status, 401)
        status, raw, _ = self.request("GET", "/api/providers", token=connector.PAIR_TOKEN)
        self.assertEqual(status, 200)
        self.assertIn("flow_agent", json.loads(raw)["providers"])

    def test_project_draft_round_trip_and_mutation_auth(self):
        project = {"id": "p-test", "title": "Bản nháp", "scenes": [{"duration": 8}]}
        status, _, _ = self.request("POST", "/api/projects", body=project)
        self.assertEqual(status, 401)
        status, raw, _ = self.request("POST", "/api/projects", token=connector.PAIR_TOKEN, body=project)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(raw)["saved"])
        status, raw, _ = self.request("GET", "/api/projects", token=connector.PAIR_TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["projects"][0]["project"]["title"], "Bản nháp")

    def test_video_submission_is_explicitly_not_implemented(self):
        status, raw, _ = self.request("POST", "/api/jobs", token=connector.PAIR_TOKEN, body={"confirmed": True})
        self.assertEqual(status, 409)
        self.assertIn("Chưa gửi gì", json.loads(raw)["error"])

    def test_chrome_headless_desktop_and_mobile_load(self):
        candidates = [shutil.which("chrome"), r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                      r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
        chrome = next((p for p in candidates if p and Path(p).is_file()), None)
        if not chrome:
            self.skipTest("Chrome không được cài đặt.")
        for viewport in ("1440,1000", "390,844"):
            with TemporaryDirectory() as profile:
                result = subprocess.run([chrome, "--headless", "--disable-gpu", "--no-first-run",
                                         "--no-default-browser-check", "--disable-extensions",
                                         "--disable-background-networking", "--disable-features=Translate",
                                         "--user-data-dir=" + profile, "--window-size=" + viewport,
                                         "--virtual-time-budget=1500", "--dump-dom",
                                         "http://127.0.0.1:18765/"], capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=25)
            self.assertEqual(result.returncode, 0, result.stderr[-1000:])
            self.assertIn("CINEMA NOVA", result.stdout)
            self.assertIn("TẠO VIDEO • CHƯA CÓ ADAPTER SẢN XUẤT", result.stdout)

    def test_frontend_scripted_workflow(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js không được cài đặt.")
        result = subprocess.run([node, "tests/frontend_smoke.js"], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Frontend draft", result.stdout)


if __name__ == "__main__":
    unittest.main()
