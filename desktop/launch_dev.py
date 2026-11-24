"""Start the patched upstream development GUI; no release packaging or updates."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def main():
    upstream=ROOT/"upstream"
    if not (upstream/"LOCAL_LONGCTX_PREVIEW.txt").is_file():
        raise SystemExit("Prepare the pinned source first")
    pnpm=shutil.which("pnpm")
    if not pnpm:
        raise SystemExit("Install the upstream-required Node.js and pnpm versions")
    env={k:v for k,v in os.environ.items() if not k.startswith(("DSH_DESKTOP_AUTO_UPDATE","DSH_DESKTOP_MANDATORY_UPDATE","DOWNLOAD_"))}
    env.update(LOCAL_LONGCTX_DEV_ROOT=str(ROOT.parent),LOCAL_LONGCTX_PYTHON=sys.executable,DSH_DESKTOP_APP_ID="org.locallongctx.studio")
    # Development only. Upstream dependencies must be installed and reviewed separately.
    return subprocess.call([pnpm,"run","dev:desktop"],cwd=upstream,env=env,shell=False)
if __name__=="__main__":
    raise SystemExit(main())
