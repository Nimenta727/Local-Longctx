"""Command-line diagnostics and local runtime / 命令行诊断与本地运行服务。"""
import argparse
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from dataclasses import asdict, replace
from pathlib import Path
from . import __version__
from .cache_profile import restore
from .config import Config, memory_plan
from .backend import BackendError, require_free, clean_env
from .compact import evaluate, Snapshot, Segment
from .service import Server
from .hardware import detect
from .scheduler import choose, report
from .freetoken import FreeTokenBackend, command as ft_command, launcher

def run(c):
    key = os.environ.get("LOCAL_LONGCTX_API_KEY") or secrets.token_urlsafe(32)
    if len(key)<24 or not key.isascii() or any(ch.isspace() for ch in key):
        raise ValueError("LOCAL_LONGCTX_API_KEY must be a long ASCII secret / 密钥必须为足够长的 ASCII 字符串")
    require_free(c.api_port)
    decision = choose(c, detect(c.state_dir))
    c = replace(c, threads=decision.threads)
    backend = FreeTokenBackend(c, decision)
    server = worker = None
    try:
        backend.start()
        server = Server(c, backend, key)
        server.cache_profile = restore(backend, c)
        print(f"Local-Longctx API: http://127.0.0.1:{c.api_port} | native window / 原生窗口: {c.context}",flush=True)
        if "LOCAL_LONGCTX_API_KEY" not in os.environ:
            print("Session key / 会话密钥（请保密）: "+key,flush=True)
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        while backend.proc.poll() is None:
            time.sleep(.5)
        raise BackendError("backend exited / 推理后端已退出")
    finally:
        if server:
            if worker and worker.is_alive():
                server.shutdown()
            server.server_close()
        backend.close()

def main(argv=None):
    p=argparse.ArgumentParser(prog="longctx",description="Local-Longctx Studio / 本地 MoE 推理控制层")
    p.add_argument("--version",action="version",version=__version__)
    p.add_argument("--config",default="config.local.json",help="configuration path / 配置文件路径")
    sub=p.add_subparsers(dest="action",required=True)
    sub.add_parser("plan",help="resource estimate / 资源预算")
    cp=sub.add_parser("compact-plan",help="evaluate offline ACE snapshot / 离线压缩决策")
    cp.add_argument("snapshot")
    sub.add_parser("hardware",help="inspect resources / 检测硬件")
    sub.add_parser("doctor",help="check engine flags / 检查引擎参数")
    sub.add_parser("serve",help="start local API / 启动本地服务")
    a=p.parse_args(argv)
    try:
        if a.action=="compact-plan":
            raw=json.loads(Path(a.snapshot).read_text(encoding="utf-8"))
            decision=evaluate(Snapshot(**raw["snapshot"]),[Segment(**x) for x in raw.get("segments",[])])
            print(json.dumps(asdict(decision),indent=2))
            return 0
        c=Config.load(a.config)
        if a.action in ("plan","hardware"):
            r=report(c)
            if a.action=="plan":
                r["native_kv_estimate"]=memory_plan(c)
            print(json.dumps(r,indent=2))
        elif a.action=="doctor":
            d=choose(c,detect(c.state_dir))
            result=subprocess.run([*launcher(c),"serve","--help"],env=clean_env(),
                                  stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30,check=True)
            flags={x for x in ft_command(c,d)[2:] if x.startswith("--")}
            missing=sorted(x for x in flags if x not in result.stdout)
            print(json.dumps({"missing_flags":missing,"note":"Help check only / 仅检查帮助参数，仍需实际加载模型"},ensure_ascii=False,indent=2))
            return int(bool(missing))
        else:
            run(c)
    except KeyboardInterrupt:
        return 130
    except (OSError,ValueError,TypeError,KeyError,BackendError,subprocess.SubprocessError) as exc:
        print("Local-Longctx: "+str(exc),file=sys.stderr)
        return 1
    return 0
