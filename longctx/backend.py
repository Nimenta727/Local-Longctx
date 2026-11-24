"""Shared transport and lifecycle for FreeToken."""
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

def clean_env():
    return {k:v for k,v in os.environ.items() if not k.startswith("FREETOKEN_")}

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
        raise NotImplementedError("use FreeTokenBackend")

    def close(self):
        try:
            stop_process(self.proc)
        finally:
            if self.log is not None:
                self.log.close()
                self.log = None
