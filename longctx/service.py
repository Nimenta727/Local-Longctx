"""Loopback-only OpenAI-compatible text gateway, single active request."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import http.client
import json
import threading
import sqlite3
import time
from .planner import prepare, RequestError
from .backend import BackendError
from .session_store import Store, Conflict
from .managed import dispatch

MAX_BODY = 32 * 1024 * 1024

class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, config, backend, key):
        self.config, self.backend, self.key = config, backend, key
        self.active = threading.Lock()
        self.sessions = None
        super().__init__(("127.0.0.1", config.api_port), Handler)

class Handler(BaseHTTPRequestHandler):
    server_version = "Local-Longctx/0.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, fmt, *args):
        # Do not include request paths, prompt text or authorization headers.
        pass

    def reply(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def error_json(self, status, message):
        self.reply(status, {"error": {"message": message, "type": "local_longctx_error"}})

    def authorized(self):
        # No CORS support, no access from browser origins, no reverse proxy trust.
        if self.headers.get("Host") != "127.0.0.1:" + str(self.server.server_port) or self.headers.get("Origin"):
            self.error_json(403, "loopback host required")
            return False
        supplied = self.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode(), ("Bearer " + self.server.key).encode()):
            self.error_json(401, "authentication required")
            return False
        return True

    def do_GET(self):
        if not self.authorized():
            return
        c = self.server.config
        if self.path == "/v1/models":
            self.reply(200, {"object": "list", "data": [{"id": c.model_id,
                       "object": "model", "owned_by": "local-longctx"}]})
        elif self.path == "/health":
            try:
                status = self.server.backend.json("/health", timeout=2)
                self.reply(200 if status.get("status") == "ok" else 503, status)
            except (OSError, ValueError, http.client.HTTPException, BackendError):
                self.error_json(503, "backend unavailable")
        elif self.path == "/local/desktop/capabilities":
            from .desktop_contract import describe
            self.reply(200, describe(c))
        elif self.path == "/local/plan":
            from .config import memory_plan
            self.reply(200, memory_plan(c))
        else:
            self.error_json(404, "unknown endpoint")

    def do_POST(self):
        if not self.authorized():
            return
        managed = self.path in ("/local/session/create","/local/session/read",
                                "/local/session/append","/local/session/rollback","/local/session/compact")
        settings_preview = self.path == "/local/desktop/settings/preview"
        if self.path != "/v1/chat/completions" and not managed and not settings_preview:
            self.error_json(404, "unknown endpoint")
            return
        if self.headers.get("Transfer-Encoding"):
            self.error_json(400, "chunked request bodies unsupported")
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY:
                self.error_json(413, "request body size out of range")
                return
            if self.headers.get_content_type() != "application/json":
                self.error_json(415, "application/json required")
                return
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError("incomplete body")
            body = json.loads(raw)
        except (ValueError, OSError, RecursionError):
            self.error_json(400, "invalid JSON request")
            return
        if not self.server.active.acquire(blocking=False):
            self.error_json(429, "another inference is active")
            return
        conn = None
        started = False
        start = time.monotonic()
        plan = None
        try:
            if settings_preview:
                from .desktop_contract import preview
                self.reply(200, preview(self.server.config, body))
                return
            if managed:
                if self.server.sessions is None:
                    self.server.sessions = Store(self.server.config.state_dir)
                payload=dispatch(self.server.sessions,self.server.backend,self.server.config,self.path,body)
                self.reply(200,payload)
                return
            plan, outbound = prepare(body, self.server.config, self.server.backend)
            conn, res = self.server.backend.request("/v1/chat/completions", outbound)
            if res.status != 200:
                self.error_json(502, "inference rejected by backend (HTTP %d)" % res.status)
                return
            streaming = outbound.get("stream", False)
            kind = res.getheader("Content-Type", "")
            if streaming and "text/event-stream" not in kind:
                self.error_json(502, "backend did not return SSE")
                return
            if not streaming:
                raw = res.read(64 * 1024 * 1024 + 1)
                if len(raw) > 64 * 1024 * 1024:
                    raise BackendError("response too large")
                payload = json.loads(raw)
                self.reply(200, payload)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            started = True
            self.close_connection = True
            # http.client decodes upstream chunk framing; preserve SSE lines.
            while True:
                line = res.readline(1024 * 1024)
                if not line:
                    break
                self.wfile.write(line)
                self.wfile.flush()
        except Conflict as exc:
            self.error_json(409,str(exc))
        except RequestError as exc:
            self.error_json(400, str(exc))
        except (ValueError,KeyError,TypeError) as exc:
            if managed or settings_preview:
                self.error_json(400,"local request rejected: "+str(exc))
            elif not started:
                self.error_json(502,"invalid backend response")
        except (OSError, http.client.HTTPException, BackendError, sqlite3.Error):
            if not started:
                try:
                    self.error_json(502, "backend or client connection failed")
                except OSError:
                    pass
            # Once SSE has begun, terminate the stream rather than forging DONE.
        finally:
            if conn is not None:
                conn.close()
            self.server.active.release()
            if plan is not None:
                print("request mode=%s estimated_input=%d output_cap=%d elapsed=%.2fs" %
                      (plan.mode, plan.prompt_tokens, plan.output_tokens, time.monotonic()-start),
                      flush=True)
