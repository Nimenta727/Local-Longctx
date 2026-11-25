"""Launch FarStack's first-party desktop without a Harness checkout."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    pnpm = shutil.which("pnpm") or shutil.which("npm")
    if not pnpm:
        raise SystemExit("Install Node.js and run npm install in desktop.")
    env = {**os.environ, "LOCAL_LONGCTX_DEV_ROOT": str(ROOT.parent), "LOCAL_LONGCTX_PYTHON": sys.executable}
    if env.get("LOCAL_LONGCTX_DATA_DIR"):
        env["FARSTACK_USER_DATA"] = str(Path(env["LOCAL_LONGCTX_DATA_DIR"]).expanduser().resolve() / "electron-user-data")
    return subprocess.call([pnpm,"run","start"], cwd=ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
