"""Source candidate gate / 源码候选版本检查。Does not publish / 不自动发行。"""
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def main():
    for args in (
        ["-m","compileall","-q","longctx","desktop","benchmarks","tests","scripts"],
        ["-m","unittest","discover","-s","tests","-v"],
        ["-m","longctx","compact-plan","configs/compact.example.json"],
    ):
        subprocess.run([sys.executable,*args],cwd=ROOT,check=True)
    print("Source checks passed / 源码检查通过; desktop/GPU not verified / 桌面及 GPU 未验证")
if __name__=="__main__":main()
