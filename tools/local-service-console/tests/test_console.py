import json
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from supervisor import Supervisor, process_for
import server


class DummySupervisor(Supervisor):
    def _build_command(self, key, run_id):
        if key == "tunnel":
            return [sys.executable, "-u", "-c",
                    "import time;print('ready',flush=True);time.sleep(60)"]
        return super()._build_command(key, run_id)


class ProcessTests(unittest.TestCase):
    def test_owned_start_log_and_stop(self):
        with tempfile.TemporaryDirectory() as path:
            mgr = DummySupervisor(state_dir=Path(path), config={})
            try:
                self.assertEqual(mgr.status("tunnel")["state"], "stopped")
                self.assertIn("已发送", mgr.start("tunnel"))
                owned = mgr.owned["tunnel"]
                self.assertIsNotNone(process_for(owned))
                self.assertIn(mgr.status("tunnel")["state"], ("running", "starting"))
                self.assertIn("重复启动", mgr.start("tunnel"))
                for _ in range(30):
                    if "ready" in mgr.log_path("tunnel").read_text(encoding="utf-8"):
                        break
                    time.sleep(0.1)
                self.assertIn("ready", mgr.log_path("tunnel").read_text(encoding="utf-8"))
                self.assertIn("已停止", mgr.stop("tunnel"))
                self.assertEqual(mgr.status("tunnel")["state"], "stopped")
            finally:
                if mgr.owned.get("tunnel"):
                    mgr.stop("tunnel")

    @unittest.skipUnless(sys.platform == "win32", "Requires Windows WSL bridge")
    def test_wsl_group_start_stop(self):
        from unittest.mock import patch
        from supervisor import WSL_COMMANDS
        original = WSL_COMMANDS["frontend"]
        WSL_COMMANDS["frontend"] = (
            "exec python -u -c 'import time;print(\"wsl-probe-ready\",flush=True);time.sleep(60)'"
        )
        with tempfile.TemporaryDirectory() as path:
            mgr = Supervisor(state_dir=Path(path))
            try:
                # A separate Vite may occupy :5173; this probe never binds that port.
                with patch("supervisor.port_open", return_value=False):
                    mgr.start("frontend")
                for _ in range(100):
                    file = mgr.log_path("frontend")
                    if file.exists() and "wsl-probe-ready" in file.read_text(encoding="utf-8", errors="replace"):
                        break
                    time.sleep(0.1)
                self.assertIn("wsl-probe-ready", mgr.log_path("frontend").read_text(encoding="utf-8"))
                self.assertIn("已停止", mgr.stop("frontend"))
                self.assertFalse(mgr.status("frontend")["managed"])
            finally:
                WSL_COMMANDS["frontend"] = original
                if mgr.owned.get("frontend"):
                    mgr.stop("frontend")

    def test_recover_owned_pid_after_manager_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            first = DummySupervisor(state_dir=path, config={})
            first.start("tunnel")
            try:
                second = DummySupervisor(state_dir=path, config={})
                self.assertTrue(second.status("tunnel")["managed"])
                second.stop("tunnel")
                self.assertFalse(second.status("tunnel")["managed"])
            finally:
                handle = first.handles.get("tunnel")
                if handle:
                    handle.wait(timeout=4)

    def test_stale_pid_never_stops_external_process(self):
        with tempfile.TemporaryDirectory() as path:
            mgr = DummySupervisor(state_dir=Path(path), config={})
            external = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(20)"])
            try:
                mgr.owned["tunnel"] = {"pid": external.pid, "created": 1, "run_id": "bad"}
                mgr.stop("tunnel")
                self.assertIsNone(external.poll())
            finally:
                external.terminate()
                external.wait(timeout=10)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.httpd = server.Server(("127.0.0.1", 0), server.Handler)
        import threading
        self.worker = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.worker.start()
        self.url = "http://127.0.0.1:" + str(self.httpd.server_port)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.worker.join(timeout=2)

    def request(self, path, *, method="GET", headers=None):
        req = urllib.request.Request(self.url + path, method=method, headers=headers or {})
        return urllib.request.urlopen(req, timeout=5)

    def test_page_and_service_data(self):
        with self.request("/") as res:
            self.assertIn(b"Poeticus", res.read())
        with self.request("/api/services") as res:
            body = json.load(res)
        self.assertEqual(len(body["services"]), 7)

    def test_post_requires_token_and_origin(self):
        path = "/api/services/invalid/start"
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.request(path, method="POST")
        self.assertEqual(cm.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.request(path, method="POST", headers={"X-Console-Token": server.TOKEN, "Origin":"https://evil.example"})
        self.assertEqual(cm.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.request(path, method="POST", headers={"X-Console-Token": server.TOKEN})
        self.assertEqual(cm.exception.code, 404)

    def test_log_sse_receives_append_after_connect(self):
        with tempfile.TemporaryDirectory() as folder:
            real = server.SUPERVISOR
            try:
                server.SUPERVISOR = DummySupervisor(state_dir=Path(folder), config={})
                file = server.SUPERVISOR.log_path("backend")
                file.write_text("initial\\n", encoding="utf-8")
                with self.request("/api/services/backend/events") as res:
                    # Server sends retry, initial event, and ping lines.
                    for _ in range(5):
                        res.readline()
                    with file.open("a", encoding="utf-8") as stream:
                        stream.write("line-added-later\\n")
                    observed = []
                    for _ in range(10):
                        line = res.readline()
                        observed.append(line)
                        if b"line-added-later" in line:
                            break
                self.assertTrue(any(b"line-added-later" in l for l in observed))
            finally:
                server.SUPERVISOR = real

    def test_log_sse(self):
        with tempfile.TemporaryDirectory() as folder:
            real = server.SUPERVISOR
            try:
                server.SUPERVISOR = DummySupervisor(state_dir=Path(folder), config={})
                server.SUPERVISOR.log_path("frontend").write_text("SSE sample\n", encoding="utf-8")
                with self.request("/api/services/frontend/events") as res:
                    lines = [res.readline() for _ in range(4)]
                self.assertIn(b"text/event-stream", res.headers["Content-Type"].encode())
                self.assertTrue(any(b"SSE sample" in line for line in lines))
            finally:
                server.SUPERVISOR = real


if __name__ == "__main__":
    unittest.main()
