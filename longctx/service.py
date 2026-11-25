"""Authenticated local Messages/text gateway / 本地鉴权推理网关。"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import http.client
import json
import threading
import sqlite3
import time
from . import __version__
from .planner import prepare, RequestError
from .backend import BackendError, parse_backend_object, reject_constant
from .session_store import Store, Conflict
from .managed import dispatch
from .native_messages import prepare_native, validate_prompt, count_native
from .harness_ace import assess

MAX_BODY = 32 * 1024 * 1024

class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, config, backend, key):
        self.config, self.backend, self.key = config, backend, key
        self.active = threading.Lock()
        self.sessions = None
        self.cache_profile = "default"
        self.desktop_worker_pid = None
        super().__init__(("127.0.0.1", config.api_port), Handler)

class Handler(BaseHTTPRequestHandler):
    server_version = "Local-Longctx/" + __version__

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
        if self.path in ("/v1/messages","/v1/messages/count_tokens"):
            kind = "authentication_error" if status == 401 else "rate_limit_error" if status == 429 else "invalid_request_error" if status < 500 else "api_error"
            self.reply(status, {"type":"error","error":{"message":message,"type":kind}})
        else:
            self.reply(status, {"error": {"message": message, "type": "local_longctx_error"}})

    def authorized(self):
        # No CORS support, no access from browser origins, no reverse proxy trust.
        if self.headers.get("Host") != "127.0.0.1:" + str(self.server.server_port) or self.headers.get("Origin"):
            self.error_json(403, "loopback host required")
            return False
        supplied = self.headers.get("Authorization", "")
        native = self.path in ("/v1/messages","/v1/messages/count_tokens")
        valid = hmac.compare_digest(supplied.encode(), ("Bearer " + self.server.key).encode())
        if native and not supplied:
            valid = hmac.compare_digest(self.headers.get("x-api-key","").encode(),self.server.key.encode())
        if not valid:
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
            payload = describe(c)
            if self.server.desktop_worker_pid is not None:
                payload["worker_pid"] = self.server.desktop_worker_pid
            self.reply(200, payload)
        elif self.path == "/local/cache/status":
            from .cache_control import snapshot
            try:
                self.reply(200,dict(snapshot(self.server.backend,c), profile=self.server.cache_profile))
            except (OSError,ValueError,KeyError,TypeError,BackendError,http.client.HTTPException):
                self.error_json(503,"native cache telemetry unavailable")
        elif self.path == "/local/plan":
            from .config import memory_plan
            self.reply(200, memory_plan(c))
        else:
            self.error_json(404, "unknown endpoint")

    def do_POST(self):
        if not self.authorized():
            return
        managed = self.path in ("/local/session/create","/local/session/read",
                                "/local/session/append","/local/session/rollback","/local/session/compact",
                                "/local/session/recall")
        settings_preview = self.path == "/local/desktop/settings/preview"
        native = self.path in ("/v1/messages","/v1/messages/count_tokens")
        ace_plan = self.path == "/local/ace/harness-plan"
        cache_apply = self.path == "/local/cache/apply"
        if self.path != "/v1/chat/completions" and not managed and not settings_preview and not native and not ace_plan and not cache_apply:
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
            body = json.loads(raw, parse_constant=reject_constant)
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
            if cache_apply:
                from .cache_control import rebuild
                from .cache_profile import save
                result = rebuild(self.server.backend,self.server.config,body)
                try:
                    applied = {name: result["snapshot"]["pools"][name]["value"]
                               for name in body["changes"]}
                    save(self.server.backend,self.server.config,applied)
                    self.server.cache_profile = "saved"
                except (OSError, ValueError, TypeError):
                    self.server.cache_profile = "unavailable"
                self.reply(200,dict(result, profile=self.server.cache_profile))
                return
            if ace_plan:
                self.reply(200,assess(self.server.backend,self.server.config,body))
                return
            if native and self.path.endswith("/count_tokens"):
                self.reply(200,{"input_tokens":count_native(self.server.backend,validate_prompt(body,self.server.config,True))})
                return
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
            if native:
                plan,outbound = prepare_native(body,self.server.config,self.server.backend)
            else:
                plan,outbound = prepare(body,self.server.config,self.server.backend)
            conn, res = self.server.backend.request("/v1/messages" if native else "/v1/chat/completions", outbound)
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
                payload = parse_backend_object(raw)
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
                if len(line) == 1024 * 1024 and not line.endswith(b"\n"):
                    raise BackendError("SSE line exceeds limit")
                self.wfile.write(line)
                self.wfile.flush()
        except Conflict as exc:
            self.error_json(409,str(exc))
        except RequestError as exc:
            self.error_json(400, str(exc))
        except (ValueError,KeyError,TypeError) as exc:
            if managed or settings_preview or ace_plan or cache_apply:
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
