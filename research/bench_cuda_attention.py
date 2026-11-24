"""Run on NVIDIA hardware with an installed compatible PyTorch. Not a model benchmark."""
import argparse,time
import torch
from cuda_attention import attention

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--tokens",type=int,default=32768)
    p.add_argument("--page",type=int,default=256)
    a=p.parse_args()
    if not torch.cuda.is_available():raise SystemExit("CUDA unavailable; no benchmark")
    if not 1<=a.tokens<=1000000 or not 1<=a.page<=4096:raise SystemExit("invalid benchmark size")
    torch.manual_seed(42)
    q=torch.randn(128,device="cuda")
    k=torch.randn(a.tokens,128)
    v=torch.randn(a.tokens,128)
    # Validate on a bounded subset against dense GPU attention.
    n=min(a.tokens,8192)
    def pages(n):return ((k[i:min(i+a.page,n)],v[i:min(i+a.page,n)]) for i in range(0,n,a.page))
    result=attention(q,pages(n))
    want=torch.softmax(k[:n].cuda()@q/128**.5,0)@v[:n].cuda()
    torch.testing.assert_close(result,want,atol=2e-5,rtol=2e-4)
    del result,want
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    start=time.perf_counter()
    result=attention(q,pages(a.tokens))
    torch.cuda.synchronize()
    print({"tokens":a.tokens,"seconds":time.perf_counter()-start,"peak_allocated_bytes":torch.cuda.max_memory_allocated(),"finite":bool(torch.isfinite(result).all()),"dense_check_tokens":n})
if __name__=="__main__":main()
