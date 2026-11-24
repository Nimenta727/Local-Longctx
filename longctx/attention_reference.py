"""CPU correctness oracle for single-query blockwise attention.

This is not a FreeToken CUDA backend. Float64-like Python arithmetic, bounded
working storage per page, no model-specific RoPE/GQA/SWA semantics.
"""
from math import exp, sqrt, inf, isfinite, fsum

def dot(a,b):
    if len(a)!=len(b) or not a:
        raise ValueError("invalid vector dimensions")
    return fsum(x*y for x,y in zip(a,b))

def streaming_attention(query,pages):
    if not query or not all(isfinite(x) for x in query):
        raise ValueError("invalid query")
    scale=1/sqrt(len(query))
    maximum=-inf
    normalizer=0.0
    accumulator=None
    for keys,values in pages:
        if len(keys)!=len(values):
            raise ValueError("K/V page mismatch")
        if not keys:
            continue
        logits=[dot(query,k)*scale for k in keys]
        if not all(isfinite(x) for x in logits):
            raise ValueError("non-finite logits")
        if accumulator is None:
            if not values[0]:
                raise ValueError("empty value dimension")
            accumulator=[0.0]*len(values[0])
        if any(len(v)!=len(accumulator) or not all(isfinite(x) for x in v) for v in values):
            raise ValueError("invalid values")
        peak=max(maximum,max(logits))
        old_scale=exp(maximum-peak) if maximum!=-inf else 0.0
        weights=[exp(x-peak) for x in logits]
        normalizer=normalizer*old_scale+fsum(weights)
        accumulator=[a*old_scale+fsum(w*v[j] for w,v in zip(weights,values)) for j,a in enumerate(accumulator)]
        maximum=peak
    if accumulator is None or normalizer<=0:
        raise ValueError("no visible KV entries")
    return [a/normalizer for a in accumulator]

def page_bounds(keys):
    if not keys or not keys[0]:
        raise ValueError("empty key page")
    d=len(keys[0])
    if any(len(k)!=d or not all(isfinite(x) for x in k) for k in keys):
        raise ValueError("invalid keys")
    return tuple(min(k[i] for k in keys) for i in range(d)),tuple(max(k[i] for k in keys) for i in range(d))

def upper_bound(query,bounds):
    lo,hi=bounds
    if not query or len(query)!=len(lo) or len(lo)!=len(hi):
        raise ValueError("bound dimensions")
    if any(not isfinite(q) or not isfinite(a) or not isfinite(b) or a>b for q,a,b in zip(query,lo,hi)):
        raise ValueError("invalid bound")
    return fsum(q*(b if q>=0 else a) for q,a,b in zip(query,lo,hi))/sqrt(len(query))

def select_pages(query,bounds,budget,pinned=()):
    """Approximate ranking by upper logit bound; never drops pinned pages."""
    if type(budget) is not int or not 1<=budget<=len(bounds):
        raise ValueError("invalid page budget")
    keep=set(pinned)
    if any(type(i) is not int or not 0<=i<len(bounds) for i in keep) or len(keep)>budget:
        raise ValueError("invalid pinned pages")
    scores=[upper_bound(query,b) for b in bounds]
    ranked=sorted((i for i in range(len(bounds)) if i not in keep),key=lambda i:(-scores[i],i))
    keep.update(ranked[:budget-len(keep)])
    return sorted(keep)
