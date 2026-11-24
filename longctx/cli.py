"""Local-Longctx launcher: plan, serve, export provider config, desktop preview."""
import argparse
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from .config import Config, memory_plan
from .backend import Backend, BackendError, require_free, command, clean_env
from .service import Server
from .openclaw import Gateway, configuration
from dataclasses import replace
from .hardware import detect
from .scheduler import choose, report
from .freetoken import FreeTokenBackend, command as ft_command

def run(c, desktop=None):
    key = os.environ.get("LOCAL_LONGCTX_API_KEY") or secrets.token_urlsafe(32)
    if len(key) < 24 or not key.isascii() or any(ch.isspace() for ch in key):
        raise ValueError("LOCAL_LONGCTX_API_KEY must be a long ASCII secret")
    require_free(c.api_port)
    decision = choose(c, detect(c.state_dir))
    c = replace(c, threads=decision.threads)
    print("Engine: " + decision.engine + " | " + decision.reason, flush=True)
    backend = FreeTokenBackend(c, decision) if decision.engine == "freetoken" else Backend(c)
    server = None
    gateway = None
    worker = None
    try:
        backend.start()
        server = Server(c, backend, key)
        print("Local-Longctx API http://127.0.0.1:%d/v1 | %s | %d total tokens" %
              (c.api_port, "freetoken-native-experimental" if decision.engine=="freetoken" else c.mode, c.context), flush=True)
        if desktop:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            gateway = Gateway(c, key, desktop)
            gateway.start()
            # Wait for upstream readiness before asking it to open the UI.
            import http.client
            deadline = time.monotonic() + 90
            ready = False
            while time.monotonic() < deadline:
                if gateway.proc.poll() is not None:
                    raise BackendError("OpenClaw exited; inspect gateway.log")
                conn = http.client.HTTPConnection("127.0.0.1", c.gateway_port, timeout=2)
                try:
                    conn.request("GET", "/readyz")
                    if conn.getresponse().status == 200:
                        ready = True
                        break
                except OSError:
                    pass
                finally:
                    conn.close()
                time.sleep(0.5)
            if not ready:
                raise BackendError("OpenClaw readiness timeout; inspect gateway.log")
            gateway.dashboard()
            while gateway.proc.poll() is None and backend.proc.poll() is None:
                time.sleep(0.5)
            raise BackendError("local child process exited")
        else:
            if "LOCAL_LONGCTX_API_KEY" not in os.environ:
                print("Session API key (keep private): " + key, flush=True)
            # Keep supervisor responsive to process exits.
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            while backend.proc.poll() is None:
                time.sleep(0.5)
            raise BackendError("backend exited")
    finally:
        if gateway:
            gateway.close()
        if server:
            if worker and worker.is_alive():
                server.shutdown()
            server.server_close()
        backend.close()

def main(argv=None):
    p = argparse.ArgumentParser(prog="longctx", description="Local-Longctx inference platform")
    p.add_argument("--config", default="config.local.json")
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("plan")
    sub.add_parser("hardware")
    sub.add_parser("doctor")
    sub.add_parser("serve")
    sub.add_parser("openclaw-config")
    desktop = sub.add_parser("desktop")
    desktop.add_argument("--openclaw", required=True)
    a = p.parse_args(argv)
    try:
        c = Config.load(a.config)
        if a.action in ("plan", "hardware"):
            r=report(c)
            if a.action=="plan":
                r["llama_baseline_estimate"]=memory_plan(c)
            print(json.dumps(r, indent=2))
        elif a.action == "doctor":
            d=choose(c,detect(c.state_dir))
            args=[str(c.freetoken_server),"serve","--help"] if d.engine=="freetoken" else [str(c.server),"--help"]
            result = subprocess.run(args, env=clean_env(),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, timeout=30, check=True)
            selected=ft_command(c,d) if d.engine=="freetoken" else command(c)
            flags = [x for x in selected[1:] if x.startswith("--")]
            missing = [x for x in flags if x not in result.stdout]
            print(json.dumps({"missing_flags": missing,
                              "note": "Help check only; actual model loading still required."}, indent=2))
            return 1 if missing else 0
        elif a.action == "openclaw-config":
            print(json.dumps(configuration(c, "${LOCAL_LONGCTX_API_KEY}",
                                           "${LOCAL_LONGCTX_GATEWAY_TOKEN}"), indent=2))
        else:
            run(c, a.openclaw if a.action == "desktop" else None)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, TypeError, BackendError, subprocess.SubprocessError) as exc:
        print("Local-Longctx: " + str(exc), file=sys.stderr)
        return 1
    return 0
