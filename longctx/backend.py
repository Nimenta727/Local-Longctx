"""Lifecycle and HTTP boundary for the upstream llama.cpp server."""
import http.client
import json
import os
import secrets
import socket
import subprocess
import time
from pathlib import Path

class BackendError(RuntimeError):
    pass

def require_free(port):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))

def command(c):
    args = [str(c.server), "--model", str(c.model), "--alias", c.model_id,
            "--host", "127.0.0.1", "--port", str(c.backend_port),
            "--ctx-size", str(c.context), "--parallel", "1",
            "--no-context-shift", "--fit", "off", "--n-gpu-layers", str(c.gpu_layers),
            "--threads", str(c.threads), "--batch-size", str(c.batch),
            "--ubatch-size", str(c.ubatch), "--cache-type-k", c.cache_type,
            "--cache-type-v", c.cache_type, "--flash-attn",
            "on" if c.cache_type != "f16" else "auto",
            "--timeout", str(c.timeout), "--jinja"]
    if c.kv_on_cpu:
        args.append("--no-kv-offload")
    if c.cpu_moe:
        args.append("--cpu-moe")
    return args

def clean_env():
    return {k: v for k, v in os.environ.items()
            if not k.startswith("LLAMA_ARG_") and k != "LLAMA_API_KEY"}

def stop_process(proc):
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)

class Backend:
    def __init__(self, config):
        self.config = config
        self.key = secrets.token_urlsafe(32)
        self.proc = None
        self.log = None

    def request(self, path, data=None, timeout=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.config.backend_port,
                                          timeout=timeout or self.config.timeout)
        headers = {"Authorization": "Bearer " + self.key}
        body = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        try:
            conn.request("GET" if data is None else "POST", path, body, headers)
            return conn, conn.getresponse()
        except BaseException:
            conn.close()
            raise

    def json(self, path, data=None, timeout=None):
        conn, res = self.request(path, data, timeout)
        try:
            if res.status != 200:
                raise BackendError("backend " + path + " returned HTTP " + str(res.status))
            raw = res.read(64 * 1024 * 1024 + 1)
            if len(raw) > 64 * 1024 * 1024:
                raise BackendError("backend response too large")
            return json.loads(raw)
        finally:
            conn.close()

    def start(self):
        c = self.config
        require_free(c.backend_port)
        c.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        env = clean_env()
        env["LLAMA_API_KEY"] = self.key
        self.log = (c.state_dir / "backend.log").open("ab")
        try:
            self.proc = subprocess.Popen(command(c), env=env, stdout=self.log,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            deadline = time.monotonic() + min(c.timeout, 1800)
            while time.monotonic() < deadline:
                if self.proc.poll() is not None:
                    raise BackendError("llama-server exited; inspect backend.log")
                try:
                    health = self.json("/health", timeout=2)
                except (OSError, http.client.HTTPException, BackendError, ValueError):
                    time.sleep(0.5)
                    continue
                if health.get("status") == "ok":
                    props = self.json("/props", timeout=10)
                    actual = props.get("default_generation_settings", {}).get("n_ctx")
                    if actual != c.context:
                        raise BackendError("configured and reported context differ: " + str(actual))
                    models = self.json("/v1/models", timeout=10)
                    if c.model_id not in [x.get("id") for x in models.get("data", [])]:
                        raise BackendError("configured model alias not advertised")
                    return
                time.sleep(0.5)
            raise BackendError("backend startup timed out")
        except BaseException:
            self.close()
            raise

    def close(self):
        try:
            stop_process(self.proc)
        finally:
            if self.log is not None:
                self.log.close()
                self.log = None
