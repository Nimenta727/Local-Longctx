"""Standalone CUDA streaming attention prototype using PyTorch kernels.
No FreeToken integration; accepts visible single-query pages in CPU or CUDA tensors.
"""
def attention(q,pages):
    import torch
    if not q.is_cuda or q.ndim!=1 or q.numel()==0:raise ValueError("CUDA query required")
    q=q.float()
    m=torch.full((),float("-inf"),device=q.device)
    z=torch.zeros((),device=q.device)
    acc=None
    for k,v in pages:
        if k.ndim!=2 or v.ndim!=2 or k.shape[0]!=v.shape[0] or k.shape[1]!=q.numel():
            raise ValueError("invalid page shape")
        if k.shape[0]==0:continue
        k=k.to(q.device,dtype=torch.float32)
        v=v.to(q.device,dtype=torch.float32)
        if acc is None:acc=torch.zeros(v.shape[1],device=q.device)
        if v.shape[1]!=acc.numel():raise ValueError("invalid value width")
        s=k@q/q.numel()**.5
        peak=torch.maximum(m,s.max())
        factor=torch.exp(m-peak)
        w=torch.exp(s-peak)
        z=z*factor+w.sum()
        acc=acc*factor+w@v
        m=peak
    if acc is None:raise ValueError("empty pages")
    return acc/z
