"""
Minimal web layer (standard library only, no Flask/FastAPI needed on a Zero W).

  GET  /              → static/index.html
  GET  /api/status    → current analysis as JSON
  GET  /api/history   → one record per second for the last 10 minutes
  POST /api/reset     → reset counters, closures and history
"""

import collections
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


class App:
    """Glue between analyzer / ADC monitor and the HTTP handlers."""

    def __init__(self, analyzer, source, adc=None, meta=None, verbose=False):
        self.analyzer = analyzer
        self.source = source
        self.adc = adc
        self.meta = meta or {}
        self.verbose = verbose
        self.history = collections.deque(maxlen=600)      # 10 min @ 1 Hz
        self._lock = threading.Lock()
        self.t_start = time.time()

    def status(self):
        s = self.analyzer.snapshot()
        s["adc"] = self.adc.snapshot() if self.adc else {"available": False}
        s["source"] = self.source.describe()
        s["meta"] = self.meta
        s["time"] = round(time.time(), 1)
        return s

    def tick(self):
        """Called once per second by the worker thread."""
        s = self.status()
        adc = s["adc"]
        rec = {
            "t": s["time"],
            "f": s["freq_hz"],
            "p": s["present"],
            "v": adc.get("v_low_last") if adc.get("available") else None,
            "vi": adc.get("v_idle") if adc.get("available") else None,
        }
        with self._lock:
            self.history.append(rec)

    def history_list(self):
        with self._lock:
            return list(self.history)

    def reset(self):
        self.analyzer.reset()
        if self.adc:
            self.adc.reset()
        with self._lock:
            self.history.clear()


class Handler(BaseHTTPRequestHandler):
    server_version = "anemotest/1.0"

    @property
    def app(self):
        return self.server.app

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                with open(os.path.join(STATIC_DIR, "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, "index.html fehlt", "text/plain; charset=utf-8")
        elif path == "/api/status":
            self._json(self.app.status())
        elif path == "/api/history":
            self._json(self.app.history_list())
        else:
            self._send(404, "Nicht gefunden", "text/plain; charset=utf-8")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/reset":
            self.app.reset()
            self._json({"ok": True})
        else:
            self._send(404, "Nicht gefunden", "text/plain; charset=utf-8")

    def log_message(self, fmt, *args):
        if self.app.verbose:
            super().log_message(fmt, *args)


def make_server(app, host="0.0.0.0", port=8080):
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    srv.app = app
    return srv
