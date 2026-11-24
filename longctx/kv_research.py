"""Experimental packed symmetric per-vector quantization (CPU reference).
Not FreeToken's KV tensor format. Never attach to production cache.
"""
import math
import struct
from dataclasses import dataclass

@dataclass(frozen=True)
class Packed:
    bits:int
    length:int
    scale:float
    data:bytes

def pack(values,bits):
    if bits not in (4,8) or not values or any(not math.isfinite(x) for x in values):
        raise ValueError("invalid vector or precision")
    maxint=(1<<(bits-1))-1
    scale=max(abs(x) for x in values)/maxint or 1.0
    # Store a real FP32 scale, so error/size match serialized representation.
    scale=struct.unpack("<f",struct.pack("<f",scale))[0]
    if not math.isfinite(scale) or scale<=0:
        raise ValueError("scale not representable")
    q=[max(-maxint,min(maxint,round(x/scale)))+maxint for x in values]
    data=bytes(q) if bits==8 else bytes(q[i]|((q[i+1] if i+1<len(q) else 0)<<4) for i in range(0,len(q),2))
    return Packed(bits,len(values),scale,data)

def unpack(p):
    if p.bits not in (4,8) or type(p.length) is not int or p.length<1 or not math.isfinite(p.scale) or p.scale<=0:
        raise ValueError("invalid packed vector")
    if len(p.data)!=(p.length*p.bits+7)//8:
        raise ValueError("invalid payload length")
    q=list(p.data) if p.bits==8 else [x for b in p.data for x in (b&15,b>>4)]
    maxint=(1<<(p.bits-1))-1
    if any(x>2*maxint for x in q[:p.length]):
        raise ValueError("invalid code")
    return [(x-maxint)*p.scale for x in q[:p.length]]

def precision(importance,access,protected=False):
    for x in (importance,access):
        if not math.isfinite(x) or not 0<=x<=1:raise ValueError("invalid score")
    return 8 if protected or max(importance,access)>=.5 else 4
