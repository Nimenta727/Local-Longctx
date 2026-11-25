"""Verify FarStack's first-party desktop source and local inference control."""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("Node.js and npm are required")
    subprocess.run([npm, "run", "check"], cwd=ROOT, check=True)
    subprocess.run([npm, "run", "test:tools"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "scripts/check_release.py"], cwd=ROOT.parent, check=True)


if __name__ == "__main__":
    main()
