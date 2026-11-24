"""Generate isolated OpenClaw configuration; reuse upstream Control UI."""
import json
import os
import secrets
import subprocess
from pathlib import Path
from .backend import require_free, stop_process

def configuration(c, api_key_ref, gateway_key_ref):
    return {
        "gateway": {"mode": "local", "bind": "loopback", "port": c.gateway_port,
                    "auth": {"mode": "token", "token": gateway_key_ref, "allowTailscale": False},
                    "tailscale": {"mode": "off"},
                    "controlUi": {"enabled": True},
                    "terminal": {"enabled": False}},
        "models": {"mode": "replace", "providers": {"longctx": {
            "baseUrl": "http://127.0.0.1:%d/v1" % c.api_port,
            "apiKey": api_key_ref, "api": "openai-completions",
            "timeoutSeconds": c.timeout,
            "models": [{"id": c.model_id, "name": "Local-Longctx",
                        "input": ["text"], "reasoning": False,
                        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                        "contextWindow": c.context, "maxTokens": c.output_reserve}]}},
        "agents": {"defaults": {"model": {"primary": "longctx/" + c.model_id,
                                         "fallbacks": []},
                                "workspace": str(c.state_dir / "workspace")}},
        "tools": {"deny": ["*"]},
        "plugins": {"enabled": False}
    }

class Gateway:
    def __init__(self, c, api_key, executable):
        self.c, self.api_key = c, api_key
        self.executable = Path(executable).resolve()
        self.proc = None
        self.log = None
        self.env = None

    def start(self):
        if not self.executable.is_file():
            raise ValueError("OpenClaw executable must be an existing trusted local file")
        # Python subprocess with shell=False cannot safely launch npm .cmd shims
        # on Windows; use an actual executable or use exported config manually.
        if self.executable.suffix.lower() in (".cmd", ".bat"):
            raise ValueError("use an executable, not a batch shim; see README")
        require_free(self.c.gateway_port)
        root = self.c.state_dir / "openclaw"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.c.state_dir / "workspace").mkdir(exist_ok=True)
        path = root / "openclaw.json"
        # Dedicated file, never overwrite the user's ordinary OpenClaw config.
        if path.exists():
            raise ValueError("isolated config already exists; use a fresh state_dir or export config")
        config = configuration(self.c, "${LOCAL_LONGCTX_API_KEY}", "${LOCAL_LONGCTX_GATEWAY_TOKEN}")
        with path.open("x", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        if os.name != "nt":
            path.chmod(0o600)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("OPENCLAW_")}
        self.env.update({"OPENCLAW_STATE_DIR": str(root), "OPENCLAW_CONFIG_PATH": str(path),
                         "LOCAL_LONGCTX_API_KEY": self.api_key,
                         "LOCAL_LONGCTX_GATEWAY_TOKEN": secrets.token_urlsafe(32)})
        self.log = (self.c.state_dir / "gateway.log").open("ab")
        try:
            self.proc = subprocess.Popen([str(self.executable), "gateway"],
                                         env=self.env, stdout=self.log,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        except BaseException:
            self.close()
            raise
        print("OpenClaw Control UI: http://127.0.0.1:%d/ (gateway token is supplied to dashboard command)" %
              self.c.gateway_port, flush=True)

    def dashboard(self):
        # Upstream command handles the dashboard's normal authentication flow.
        subprocess.run([str(self.executable), "dashboard"], env=self.env,
                       timeout=60, check=True)

    def close(self):
        try:
            stop_process(self.proc)
        finally:
            if self.log is not None:
                self.log.close()
                self.log = None
