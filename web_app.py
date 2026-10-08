"""Loopback-only browser interface for the existing local vision engine."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
import queue
import time

import cv2
import numpy as np

from vision.models import ROOT
from vision.pipeline import Config, run, source_info


class BrowserCapture:
    """One-frame mailbox: slow inference never accumulates stale camera frames."""
    def __init__(self, stop):
        self.stop = stop
        self.frames = queue.Queue(maxsize=1)

    def push(self, frame):
        try:
            self.frames.get_nowait()
        except queue.Empty:
            pass
        try:
            self.frames.put_nowait(frame)
        except queue.Full:
            pass

    def read(self):
        deadline = time.monotonic() + 15
        while not self.stop.is_set() and time.monotonic() < deadline:
            try:
                return True, self.frames.get(timeout=0.2)
            except queue.Empty:
                pass
        return False, None

    def get(self, prop):
        return 0

    def release(self):
        self.stop.set()


class Session:
    def make_identity(self):
        return None

    def __init__(self):
        self.lock = threading.Lock()
        self.worker = None
        self.stop = threading.Event()
        self.frame = None
        self.stats = {"status": "idle"}
        self.browser_capture = None
        self.capture_id = None

    def snapshot(self):
        with self.lock:
            return {**self.stats, "running": bool(self.worker and self.worker.is_alive())}

    def start(self, data):
        source = str(data.get("source", "")).strip()
        if data.get("mode") == "demo":
            source = str(ROOT / "samples" / "controlled_crossing.avi")
        browser_mode = data.get("mode") == "browser"
        if browser_mode:
            source = "0"
        config = Config(source=source, axis=str(data.get("axis", "horizontal")),
                        position=float(data.get("position", 0.5)),
                        in_positive=data.get("direction", "positive") == "positive")
        config.validate()
        source_info(config.source)
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ValueError("Stop the current session before starting another.")
            self.stop = threading.Event()
            self.browser_capture = BrowserCapture(self.stop) if browser_mode else None
            self.capture_id = secrets.token_urlsafe(24) if browser_mode else None
            self.frame = None
            self.stats = {"status": "starting"}
            self.worker = threading.Thread(target=self.process, args=(config,), daemon=True)
            self.worker.start()
            return self.capture_id

    def process(self, config):
        def update(frame, stats, events):
            ok, encoded = (False, None) if self.browser_capture else cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            with self.lock:
                self.stats = stats
                if ok:
                    self.frame = encoded.tobytes()
        try:
            result = run(config, callback=update, stop=self.stop, capture_override=self.browser_capture,
                         annotate_frames=self.browser_capture is None, identity=self.make_identity())
            with self.lock:
                self.stats = result
        except Exception:
            # Never return a credential-bearing source URL or backend exception.
            with self.lock:
                self.stats = {**self.stats, "status": "error",
                              "message": "Could not process input. Check the video path, camera connection, or installed models."}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body, content_type="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def valid_host(self):
        return self.headers.get("Host") in self.server.allowed_hosts

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {"error": "Local access only."})
        path = self.path.split("?", 1)[0]
        if path == "/":
            page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
            self.reply(200, page.replace("__TOKEN__", self.server.token).encode(), "text/html; charset=utf-8")
        elif path == "/api/status":
            self.reply(200, self.server.session.snapshot())
        elif path == "/api/frame":
            with self.server.session.lock:
                frame = self.server.session.frame
            self.reply(200 if frame else 204, frame or b"", "image/jpeg")
        else:
            self.reply(404, {"error": "Not found"})

    def do_POST(self):
        if (not self.valid_host() or
                self.headers.get("X-Session-Token") != self.server.token or
                self.headers.get("Origin") not in {None, *self.server.allowed_origins}):
            return self.reply(403, {"error": "Invalid local session."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if self.path == "/api/camera-frame":
                session = self.server.session
                if (not session.browser_capture or not session.worker or not session.worker.is_alive()
                        or self.headers.get("X-Capture-Id") != session.capture_id):
                    return self.reply(409, {"error": "Camera session ended."})
                if not 0 < length <= 1000000:
                    return self.reply(413, {"error": "Frame too large."})
                frame = cv2.imdecode(np.frombuffer(self.rfile.read(length), np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    return self.reply(400, {"error": "Invalid camera frame."})
                session.browser_capture.push(frame)
                return self.reply(200, {"ok": True})
            if not 0 <= length <= 16384:
                return self.reply(413, {"error": "Request too large."})
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("Expected an object.")
            if self.path == "/api/start":
                capture_id = self.server.session.start(data)
                return self.reply(200, {"ok": True, "capture_id": capture_id})
            elif self.path == "/api/stop":
                self.server.session.stop.set()
            else:
                return self.reply(404, {"error": "Not found"})
            self.reply(200, {"ok": True})
        except (ValueError, TypeError):
            self.reply(400, {"error": "Check input and line settings. Stop any active session first."})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.session = Session()
    server.token = secrets.token_urlsafe(32)
    server.allowed_hosts = {f"127.0.0.1:{args.port}", f"localhost:{args.port}"}
    server.allowed_origins = {f"http://{host}" for host in server.allowed_hosts}
    print(f"Maggpie Vision: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.session.stop.set()
        if server.session.worker:
            server.session.worker.join(timeout=15)
        server.server_close()


if __name__ == "__main__":
    main()
