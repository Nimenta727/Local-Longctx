"""Explicit developer verification. No publishing, no credentials, no auto updates."""
import os,subprocess,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
    up=ROOT/"upstream"
    if not (up/"LOCAL_LONGCTX_PREVIEW.txt").is_file():raise SystemExit("Prepare pinned overlay first")
    pnpm=shutil.which("pnpm")
    if not pnpm:raise SystemExit("Pinned Node/pnpm required")
    env={k:v for k,v in os.environ.items() if not k.startswith(("DSH_DESKTOP_AUTO_UPDATE","DSH_DESKTOP_MANDATORY_UPDATE","DOWNLOAD_"))}
    for command in ([sys.executable,"-m","unittest","discover","-s","tests","-v"],[pnpm,"run","typecheck"],[pnpm,"run","build"]):
        subprocess.run(command,cwd=ROOT.parent if command[0]==sys.executable else up,env=env,check=True)
    print("Build completed; still requires actual desktop launch, tool roundtrip and GPU tests.")
if __name__=="__main__":main()
