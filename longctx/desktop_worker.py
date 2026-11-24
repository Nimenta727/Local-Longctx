"""Desktop child worker; EOF stops inference / 桌面子进程，EOF 触发停止。"""
import os
import sys
import threading
from .config import Config
from .backend import require_free
from .freetoken import FreeTokenBackend
from .hardware import detect
from .scheduler import choose
from .service import Server

def run(path):
    c=Config.load(path)
    key=os.environ.get("LOCAL_LONGCTX_API_KEY","")
    if len(key)<24 or not key.isascii() or any(ch.isspace() for ch in key):
        raise ValueError("missing desktop session key")
    c.state_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    stopped=threading.Event()
    def watch():
        try:
            while sys.stdin.buffer.read(4096):
                pass
        finally:
            stopped.set()
    threading.Thread(target=watch,daemon=True).start()
    require_free(c.api_port)
    backend=FreeTokenBackend(c,choose(c,detect(c.state_dir)))
    server=None
    worker=None
    try:
        backend.start(stop_event=stopped)
        if stopped.is_set():
            return 0
        server=Server(c,backend,key)
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        while not stopped.wait(.25):
            if backend.proc.poll() is not None:
                raise RuntimeError("native engine exited")
        return 0
    finally:
        if server:
            if worker and worker.is_alive():
                server.shutdown()
            server.server_close()
        backend.close()

def main():
    if len(sys.argv)!=2:
        return 2
    try:
        return run(sys.argv[1])
    except Exception as exc:
        # Keep detailed errors local, not in renderer or remote logs.
        try:
            c=Config.load(sys.argv[1])
            c.state_dir.mkdir(parents=True,exist_ok=True)
            with (c.state_dir/"desktop-worker.log").open("a",encoding="utf-8") as fp:
                fp.write(type(exc).__name__+": "+str(exc)+"\n")
        except Exception:
            pass
        return 1

if __name__=="__main__":
    raise SystemExit(main())
