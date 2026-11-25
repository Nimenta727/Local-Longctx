"""Desktop child worker; EOF stops inference / 桌面子进程，EOF 触发停止。"""
import os
import sys
import threading
from dataclasses import replace
from .config import Config
from .cache_profile import restore
from .backend import BackendError, require_free
from .freetoken import FreeTokenBackend
from .hardware import detect
from .scheduler import choose
from .service import Server

def run(path):
    c=Config.load(path)
    if c.bundled_engine:
        from freetoken.models.gguf.reader import load_gguf_metadata, gguf_split_paths

        metadata = load_gguf_metadata(str(c.model))
        if metadata.get("general.architecture") != "qwen3moe" or len(gguf_split_paths(str(c.model))) != 1:
            raise ValueError("FarStack bundled runtime requires a single-file Qwen3 MoE GGUF")
        model_limit = metadata.get("qwen3moe.context_length")
        if type(model_limit) is not int or model_limit < 1024:
            raise ValueError("GGUF does not declare a supported context length")
        context = min(c.context, model_limit)
        c = replace(c, context=context, model_limit=min(model_limit,2097152), ubatch=min(c.ubatch,context),
                    output_reserve=min(c.output_reserve,context-257),
                    model_is_moe=True,freetoken_model_verified=True).validate()
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
        try:
            backend.start(stop_event=stopped)
        except BackendError:
            if not backend.recover_tiered_kv():
                raise
        c=backend.config
        if stopped.is_set():
            return 0
        profile=restore(backend,c)
        if stopped.is_set():
            return 0
        server=Server(c,backend,key)
        server.cache_profile=profile
        server.desktop_worker_pid=os.getpid()
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        while not stopped.wait(.25):
            if not server.active.acquire(blocking=False):
                continue
            try:
                if not server.recover_tiered_kv() and backend.proc.poll() is not None:
                    raise RuntimeError("native engine exited")
            finally:
                server.active.release()
        return 0
    finally:
        if server:
            if worker and worker.is_alive():
                server.shutdown()
            server.server_close()
        backend.close()
        if backend.kv_fault_marker is not None:
            backend.kv_fault_marker.unlink(missing_ok=True)

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
