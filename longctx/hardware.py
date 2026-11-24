"""Read-only resource detection; unknown memory is not assumed available."""
from dataclasses import dataclass
import csv
import ctypes
import os
from pathlib import Path
import platform
import shutil
import subprocess

GIB = 1024**3

@dataclass(frozen=True)
class GPU:
    uuid: str
    name: str
    free_gib: float
    total_gib: float
    driver: str

@dataclass(frozen=True)
class Hardware:
    os: str
    threads: int
    ram_total_gib: float | None
    ram_available_gib: float | None
    disk_free_gib: float
    nvidia: tuple[GPU, ...]

def ram():
    try:
        if platform.system() == "Linux":
            values = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                k, v = line.split(":", 1)
                values[k] = int(v.split()[0])*1024
            return values["MemTotal"]/GIB, values["MemAvailable"]/GIB
        if platform.system() == "Windows":
            class Memory(ctypes.Structure):
                _fields_ = [("length",ctypes.c_ulong),("load",ctypes.c_ulong)] + [
                    (k,ctypes.c_ulonglong) for k in
                    ("total","available","page_total","page_available","virtual_total","virtual_available","extended_available")]
            m = Memory()
            m.length = ctypes.sizeof(m)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return m.total/GIB, m.available/GIB
    except (OSError, ValueError, KeyError):
        pass
    return None, None

def gpus():
    exe = shutil.which("nvidia-smi")
    if not exe:
        return ()
    try:
        r = subprocess.run([exe,"--query-gpu=uuid,name,memory.free,memory.total,driver_version",
                            "--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=5,check=True)
        found = []
        for row in csv.reader(r.stdout.splitlines()):
            if len(row) != 5:
                continue
            uid,name,free,total,driver = (v.strip() for v in row)
            try:
                free,total = float(free),float(total)
            except ValueError:
                continue
            if uid.startswith("GPU-") and 0 <= free <= total and total > 0:
                found.append(GPU(uid,name,free/1024,total/1024,driver))
        return tuple(found)
    except (OSError,subprocess.SubprocessError):
        return ()

def detect(path):
    p = Path(path).resolve()
    while not p.exists():
        p = p.parent
    total,available = ram()
    return Hardware(platform.system(),os.cpu_count() or 1,total,available,
                    shutil.disk_usage(p).free/GIB,gpus())
