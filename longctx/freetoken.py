"""Experimental local FreeToken adapter, no automatic downloads."""
import http.client
import subprocess
import time
from uuid import uuid4
from dataclasses import replace
from .backend import Backend,BackendError,clean_env,require_free

def launcher(c):
    return [str(c.freetoken_server), * (("-I", "-m", "freetoken.cli") if c.bundled_engine else ())]


def command(c,d):
    args = [*launcher(c),"serve","--model",str(c.model),
            "--served-model-name",c.model_id,"--host","127.0.0.1",
            "--port",str(c.backend_port),"--gpu",d.gpu_uuid,
            "--max-running-requests","1","--max-output-tokens",str(c.output_reserve),
            "--max-seq-len-override",str(c.context),"--max-prefill-length",str(d.prefill_chunk),
            "--memory-ratio",str(d.memory_ratio),"--moe-strategy",c.moe_strategy,"--cache-type","radix",
            "--kv-cache-dtype",c.kv_cache_dtype,
            "--moe-cpu-threads",str(d.threads),"--kv-reserve-tokens",str(min(c.context,c.kv_tokens or 8192)),
            "--enable-cache-report","--enable-timings-report"]
    if c.kv_tokens:
        args += ["--num-tokens",str(c.kv_tokens)]
    if c.expert_slots:
        args += ["--moe-cache-size",str(c.expert_slots)]
    if c.ssd_experts_enabled:
        args += ["--experimental-ssd-experts","--experimental-ssd-expert-staging-mib",
                 str(c.ssd_expert_staging_mib),"--cuda-graph-max-bs","0","--disable-moe-prefill-overlap"]
    if c.ssd_kv_enabled:
        args += ["--experimental-ssd-kv",str((c.state_dir / "runtime-cache" / "ssd-kv.bin").resolve()),
                 "--experimental-ssd-kv-limit-mib",str(c.ssd_kv_limit_mib)]
    if c.ssd_active_kv_enabled:
        directory=c.ssd_active_kv_dir or (c.state_dir / "runtime-cache" / "active-kv")
        args += ["--farstack-kv-dir",str(directory.resolve()),
                 "--farstack-kv-gpu-tokens",str(c.ssd_active_kv_gpu_tokens),
                 "--farstack-kv-ram-mib",str(c.ssd_active_kv_ram_mib),
                 "--farstack-kv-disk-mib",str(c.ssd_active_kv_disk_mib),"--attention-backend","triton"]
        if not c.ssd_experts_enabled:
            args += ["--cuda-graph-max-bs","0"]
    return args

class FreeTokenBackend(Backend):
    def __init__(self,c,decision):
        super().__init__(c)
        self.decision=decision
        self.kv_fault_marker=None
        self.kv_recovered=False
        self.stop_event=None

    def recover_tiered_kv(self):
        marker=self.kv_fault_marker
        if not self.config.ssd_active_kv_enabled or marker is None:
            return False
        if self.stop_event is not None and self.stop_event.is_set():
            return False
        try:
            with marker.open("rb") as signal:
                if signal.read(1)!=b"1":
                    return False
        except FileNotFoundError:
            return False
        self.close()
        marker.unlink(missing_ok=True)
        c=self.config
        # Drop the enlarged SSD pool override and let the engine size its GPU pool.
        self.config=replace(c,ssd_active_kv=False,kv_tokens=0).validate()
        self.start(stop_event=self.stop_event)
        self.kv_recovered=True
        return True

    def budget_window(self):
        raw=self.json("/v1/cache/status",timeout=5)
        data=raw.get("geometry",{})
        pages, step=data.get("num_pages"), data.get("page_size")
        if raw.get("state")!="serving" or type(pages) is not int or type(step) is not int or min(pages,step)<=0:
            raise BackendError("could not confirm current KV capacity")
        return min(self.config.context,pages*step)

    def start(self, stop_event=None):
        self.stop_event=stop_event
        c=self.config
        require_free(c.backend_port)
        c.state_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
        env={k:v for k,v in clean_env().items() if not k.startswith("FREETOKEN_")}
        cache = (c.state_dir / "runtime-cache").resolve()
        cache.mkdir(exist_ok=True, mode=0o700)
        env.pop("FARSTACK_KV_FAULT_FILE",None)
        self.kv_fault_marker=None
        if c.ssd_active_kv_enabled:
            self.kv_fault_marker=cache / ("active-kv-fault-"+uuid4().hex)
            with self.kv_fault_marker.open("xb") as marker:
                marker.write(b"0")
                marker.flush()
            env["FARSTACK_KV_FAULT_FILE"]=str(self.kv_fault_marker)
        env.update({"FREETOKEN_API_KEY":self.key,"HF_HUB_OFFLINE":"1","TRANSFORMERS_OFFLINE":"1",
                    "XDG_CACHE_HOME":str(cache),"CUDA_CACHE_PATH":str(cache / "cuda"),
                    "HF_HOME":str(cache / "huggingface"),"TORCH_HOME":str(cache / "torch")})
        self.log=(c.state_dir/"freetoken.log").open("ab")
        try:
            self.proc=subprocess.Popen(command(c,self.decision),env=env,stdout=self.log,
                                       stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
            deadline=time.monotonic()+min(c.timeout,1800)
            while time.monotonic()<deadline:
                if stop_event is not None and stop_event.is_set():
                    raise BackendError("desktop startup cancelled")
                if self.proc.poll() is not None:
                    if c.ssd_kv_enabled:
                        raise BackendError("FreeToken exited in SSD KV checkpoint mode; select the patched engine and inspect freetoken.log")
                    if c.ssd_experts_enabled:
                        raise BackendError("FreeToken exited in SSD expert mode; select the patched engine and inspect freetoken.log")
                    raise BackendError("FreeToken exited; inspect freetoken.log")
                try:
                    models=self.json("/v1/models",timeout=2)
                except (OSError,http.client.HTTPException,BackendError,ValueError):
                    time.sleep(0.5)
                    continue
                entries=[m for m in models.get("data",[]) if m.get("id")==c.model_id]
                if not entries:
                    time.sleep(0.5)
                    continue
                lengths=[entries[0][k] for k in ("max_model_len","context_length") if k in entries[0]]
                minimum = 1024 if c.bundled_engine else c.context
                if not lengths or any(type(n) is not int or not minimum<=n<=c.context for n in lengths) or len(set(lengths))!=1:
                    raise BackendError("FreeToken did not confirm requested context length")
                self.count_prompt([{"role":"user","content":"ping"}])
                if lengths[0]!=c.context:
                    actual=lengths[0]
                    self.config=replace(c,context=actual,output_reserve=min(c.output_reserve,actual-257),
                                        ubatch=min(c.ubatch,actual)).validate()
                return
            raise BackendError("FreeToken startup timed out")
        except BaseException:
            self.close()
            raise

    def count_prompt(self,messages):
        # Cross-API estimate; actual OpenAI template parity is not yet proven.
        system,turns=[],[]
        for m in messages:
            if m["role"]=="system":
                if turns:
                    raise BackendError("inline system message unsupported in experimental preflight")
                system.append(m["content"])
            else:
                turns.append(m)
        if not turns:
            raise BackendError("at least one conversation turn required")
        data={"model":self.config.model_id,"messages":turns}
        if system:
            data["system"]="\n\n".join(system)
        n=self.json("/v1/messages/count_tokens",data).get("input_tokens")
        if type(n) is not int or n<0:
            raise BackendError("invalid FreeToken token count")
        return n
