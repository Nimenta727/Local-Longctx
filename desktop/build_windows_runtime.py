"""Stage a native Windows runtime tree for the FarStack Electron installer."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("python_runtime", type=Path, help="relocatable Windows CPython 3.12 directory")
    cli.add_argument("output", type=Path, help="new runtime directory for FARSTACK_RUNTIME_DIR")
    args = cli.parse_args()
    if sys.platform != "win32":
        cli.error("build the Windows CUDA runtime on Windows with MSVC and CUDA 13")
    source, output = args.python_runtime.resolve(), args.output.resolve()
    if output.exists() or not (source / "python.exe").is_file() or source in output.parents:
        cli.error("use a relocatable python.exe and a new output directory outside the source")
    shutil.copytree(source, output)
    python = output / "python.exe"
    commands = [
        ["-m", "pip", "install", "setuptools>=68", "wheel", "ninja", "torch==2.14.1",
         "--extra-index-url", "https://download.pytorch.org/whl/cu130"],
        ["-m", "pip", "install", "--no-build-isolation", str(ROOT / "vendor" / "freetoken"),
         f"{ROOT}[ssd-research]"],
        ["-m", "pip", "check"],
        ["-c", "import torch; import longctx.desktop_worker; import freetoken.kernel._pinned_tensor; "
         "assert torch.version.cuda and torch.version.cuda.startswith('13.')"],
        ["-I", "-m", "freetoken.cli", "serve", "--help"],
    ]
    for command in commands:
        subprocess.run([str(python), *command], cwd=output, check=True)
    print(f"FARSTACK_RUNTIME_DIR={output}")


if __name__ == "__main__":
    main()
