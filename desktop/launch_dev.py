"""Start the patched upstream development GUI; no release packaging or updates."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def data_root(upstream):
    override = os.environ.get("LOCAL_LONGCTX_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    # Keep profiles created by earlier Studio launches available in place.
    desktop = upstream / "apps" / "desktop"
    for existing in (desktop / ".desktop-dev", desktop / ".desktop-build" / "development"):
        if (existing / "electron-user-data" / "local-longctx").is_dir():
            return existing.resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return (base / "Local-Longctx").resolve()

def main():
    upstream=ROOT/"upstream"
    if not (upstream/"LOCAL_LONGCTX_PREVIEW.txt").is_file():
        raise SystemExit("Prepare the pinned source first")
    pnpm=shutil.which("pnpm")
    if not pnpm:
        raise SystemExit("Install the upstream-required Node.js and pnpm versions")
    env={k:v for k,v in os.environ.items() if not k.startswith(("DSH_DESKTOP_AUTO_UPDATE","DSH_DESKTOP_MANDATORY_UPDATE","DOWNLOAD_"))}
    env.update(LOCAL_LONGCTX_DEV_ROOT=str(ROOT.parent),LOCAL_LONGCTX_PYTHON=sys.executable,DSH_DESKTOP_APP_ID="org.locallongctx.studio")
    state = data_root(upstream)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    paths = {"DSH_HOME": state / "home", "DSH_DESKTOP_USER_DATA_DIR": state / "electron-user-data"}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    env.update({key: str(value) for key, value in paths.items()})
    print("Local-Longctx data:", state, flush=True)
    # Development only. Upstream dependencies must be installed and reviewed separately.
    return subprocess.call([pnpm,"run","dev:desktop"],cwd=upstream,env=env,shell=False)
if __name__=="__main__":
    raise SystemExit(main())
