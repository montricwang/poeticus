"""Standalone localhost control plane for Poeticus services."""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from supervisor import LOOKUP, Supervisor

PORT = 8765
TOKEN = secrets.token_urlsafe(32)
SUPERVISOR = Supervisor()
ROOT = Path(__file__).resolve().parent


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format_string: str, *args) -> None:
        # Do not echo URLs and possible sensitive contents into stdout.
        pass

    def _headers(self, status=200, content_type="application/json", length=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.end_headers()

    def _send(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._headers(status=status, length=len(payload))
        self.wfile.write(payload)

    def _origin_ok(self):
        host = self.headers.get("Host", "")
        if host not in (f"localhost:{self.server.server_port}", f"127.0.0.1:{self.server.server_port}"):
            return False
        site = self.headers.get("Sec-Fetch-Site", "")
        if site not in ("", "none", "same-origin"):
            return False
        origin = self.headers.get("Origin")
        return not origin or origin in (
            f"http://localhost:{self.server.server_port}",
            f"http://127.0.0.1:{self.server.server_port}"
        )

    def do_GET(self):
        if not self._origin_ok():
            return self._send({"error": "仅允许本机同源访问"}, 403)
        path = urlsplit(self.path).path
        if path == "/":
            content = (ROOT / "index.html").read_bytes()
            self._headers(content_type="text/html; charset=utf-8", length=len(content))
            return self.wfile.write(content)
        if path == "/favicon.svg":
            content = (ROOT / "favicon.svg").read_bytes()
            self._headers(content_type="image/svg+xml", length=len(content))
            return self.wfile.write(content)
        if path == "/app.js":
            content = (ROOT / "app.js").read_bytes()
            self._headers(content_type="text/javascript; charset=utf-8", length=len(content))
            return self.wfile.write(content)
        if path == "/style.css":
            content = (ROOT / "style.css").read_bytes()
            self._headers(content_type="text/css; charset=utf-8", length=len(content))
            return self.wfile.write(content)
        if path == "/api/token":
            return self._send({"token": TOKEN})
        if path == "/api/services":
            return self._send({"services": SUPERVISOR.all_statuses()})
        log_match = re.fullmatch(r"/api/services/([a-z]+)/events", path)
        if log_match and log_match.group(1) in LOOKUP:
            return self._events(log_match.group(1))
        return self._send({"error": "未找到资源"}, 404)

    def do_POST(self):
        if not self._origin_ok() or not secrets.compare_digest(
                self.headers.get("X-Console-Token", ""), TOKEN):
            return self._send({"error": "请求被拒绝"}, 403)
        if int(self.headers.get("Content-Length", "0")) > 1024:
            return self._send({"error": "请求体过大"}, 413)
        path = urlsplit(self.path).path
        match = re.fullmatch(r"/api/services/([a-z]+)/(start|stop|restart)", path)
        bulk = re.fullmatch(r"/api/all/(start|stop)", path)
        if not match and not bulk:
            return self._send({"error": "不支持该操作"}, 404)
        try:
            if match:
                key, action = match.groups()
                if key not in LOOKUP:
                    return self._send({"error": "未知服务"}, 404)
                result = getattr(SUPERVISOR, action)(key)
                return self._send({"message": result, "service": SUPERVISOR.status(key)})
            action = bulk.group(1)
            order = list(LOOKUP) if action == "start" else list(reversed(LOOKUP))
            results = {}
            for key in order:
                try:
                    results[key] = getattr(SUPERVISOR, action)(key)
                except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
                    results[key] = "失败：" + str(exc)
            return self._send({"results": results})
        except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
            return self._send({"error": str(exc)}, 409)

    def _events(self, key: str):
        path = SUPERVISOR.log_path(key)
        try:
            offset = int(self.headers.get("Last-Event-ID", ""))
        except ValueError:
            offset = -1
        self._headers(content_type="text/event-stream; charset=utf-8")
        self.wfile.write(b"retry: 1200\n\n")
        self.wfile.flush()
        try:
            while True:
                if path.exists():
                    size = path.stat().st_size
                    if offset < 0:
                        offset = max(0, size - 24000)
                    if offset > size:
                        offset = 0
                    if size > offset:
                        with path.open("rb") as file:
                            file.seek(offset)
                            chunk = file.read(min(size - offset, 12000))
                        offset += len(chunk)
                        content = {"text": chunk.decode("utf-8", errors="replace")}
                        wire = ("id: " + str(offset) + "\ndata: " +
                                json.dumps(content, ensure_ascii=False) + "\n\n").encode("utf-8")
                        self.wfile.write(wire)
                        self.wfile.flush()
                else:
                    offset = -1
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
                time.sleep(0.4)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


class Server(ThreadingHTTPServer):
    daemon_threads = True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Poeticus local service console")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = Server(("127.0.0.1", PORT), Handler)
    address = f"http://127.0.0.1:{PORT}"
    print("Poeticus Console:", address, flush=True)
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
