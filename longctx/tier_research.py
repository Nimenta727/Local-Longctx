"""Bounded opaque page store for CPU RAM/SSD experiments; no native KV hooks."""
from collections import OrderedDict
from pathlib import Path
import hashlib
import os
import tempfile

class PageStore:
    def __init__(self,root,ram_bytes,ssd_bytes):
        if any(type(x) is not int or x<0 for x in (ram_bytes,ssd_bytes)):
            raise ValueError("invalid tier budget")
        self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        # Dedicated empty private directory; avoid overwriting unrelated data.
        if any(self.root.iterdir()):raise ValueError("use empty page directory")
        self.ram_budget,self.ssd_budget=ram_bytes,ssd_bytes
        self.ram=OrderedDict()
        self.disk={}
        self.ram_size=self.disk_size=0

    def put(self,data):
        if not isinstance(data,bytes):raise ValueError("bytes required")
        key=hashlib.sha256(data).hexdigest()
        if key in self.ram or key in self.disk:return key
        if len(data)>self.ssd_budget-self.disk_size:raise ValueError("SSD budget exhausted")
        fd,tmp=tempfile.mkstemp(dir=self.root)
        try:
            with os.fdopen(fd,"wb") as fp:
                fp.write(data);fp.flush();os.fsync(fp.fileno())
            os.replace(tmp,self.root/key)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        self.disk[key]=len(data);self.disk_size+=len(data)
        self._warm(key,data)
        return key

    def _warm(self,key,data):
        if len(data)>self.ram_budget:return
        if key in self.ram:self.ram.move_to_end(key);return
        while self.ram and self.ram_size+len(data)>self.ram_budget:
            _,old=self.ram.popitem(last=False);self.ram_size-=len(old)
        self.ram[key]=data;self.ram_size+=len(data)

    def get(self,key):
        if key not in self.disk:raise KeyError(key)
        if key in self.ram:self.ram.move_to_end(key);return self.ram[key]
        with (self.root/key).open("rb") as fp:
            data=fp.read(self.disk[key]+1)
        if len(data)!=self.disk[key] or hashlib.sha256(data).hexdigest()!=key:
            raise ValueError("page integrity failure")
        self._warm(key,data)
        return data
