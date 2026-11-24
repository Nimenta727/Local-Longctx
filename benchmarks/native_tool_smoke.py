"""Real local protocol smoke test. Uses harmless echo data; executes no tools."""
import json,os,urllib.request
def post(path,body):
    key=os.environ["LOCAL_LONGCTX_API_KEY"]
    req=urllib.request.Request("http://127.0.0.1:18080"+path,data=json.dumps(body).encode(),
        headers={"x-api-key":key,"Content-Type":"application/json","anthropic-version":"2023-06-01"})
    with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)
def main():
    prompt={"model":"local-longctx","messages":[{"role":"user","content":"Call echo with text hello."}],
            "tools":[{"name":"echo","input_schema":{"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}}],
            "tool_choice":{"type":"tool","name":"echo"}}
    print("count",post("/v1/messages/count_tokens",prompt))
    r=post("/v1/messages",dict(prompt,max_tokens=256,stream=False))
    calls=[b for b in r.get("content",[]) if b.get("type")=="tool_use"]
    if len(calls)!=1 or calls[0].get("name")!="echo":raise SystemExit("tool-call smoke failed")
    call=calls[0]
    follow=dict(prompt,tool_choice={"type":"none"},messages=prompt["messages"]+
                [{"role":"assistant","content":r["content"]},
                 {"role":"user","content":[{"type":"tool_result","tool_use_id":call["id"],"content":"hello"}]}])
    out=post("/v1/messages",dict(follow,max_tokens=256,stream=False))
    if not any(b.get("type")=="text" and b.get("text") for b in out.get("content",[])):raise SystemExit("tool-result smoke failed")
    print("PASS native tool round trip (no real tool execution)")
if __name__=="__main__":main()
