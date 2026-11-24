"""Experimental local FreeToken adapter, no automatic downloads."""
import http.client
import subprocess
import time
from .backend import Backend,BackendError,clean_env,require_free

def command(c,d):
    return [str(c.freetoken_server),"serve","--model",str(c.model),
            "--served-model-name",c.model_id,"--host","127.0.0.1",
            "--port",str(c.backend_port),"--gpu",d.gpu_uuid,
            "--max-running-requests","1","--max-output-tokens",str(c.output_reserve),
            "--max-seq-len-override",str(c.context),"--max-prefill-length",str(d.prefill_chunk),
            "--memory-ratio",str(d.memory_ratio),"--moe-strategy","auto","--cache-type","radix",
            "--kv-cache-dtype",c.kv_cache_dtype,
            "--moe-cpu-threads",str(d.threads),"--kv-reserve-tokens",str(c.context),
            "--enable-cache-report","--enable-timings-report"]

class FreeTokenBackend(Backend):
    def __init__(self,c,decision):
        super().__init__(c)
        self.decision=decision

    def start(self, stop_event=None):
        c=self.config
        require_free(c.backend_port)
        c.state_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
        env={k:v for k,v in clean_env().items() if not k.startswith("FREETOKEN_")}
        env.update({"FREETOKEN_API_KEY":self.key,"HF_HUB_OFFLINE":"1","TRANSFORMERS_OFFLINE":"1"})
        self.log=(c.state_dir/"freetoken.log").open("ab")
        try:
            self.proc=subprocess.Popen(command(c,self.decision),env=env,stdout=self.log,
                                       stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
            deadline=time.monotonic()+min(c.timeout,1800)
            while time.monotonic()<deadline:
                if stop_event is not None and stop_event.is_set():
                    raise BackendError("desktop startup cancelled")
                if self.proc.poll() is not None:
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
                if not lengths or any(type(n) is not int or n!=c.context for n in lengths):
                    raise BackendError("FreeToken did not confirm requested context length")
                self.count_prompt([{"role":"user","content":"ping"}])
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
