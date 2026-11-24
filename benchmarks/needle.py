"""Single-run text retrieval smoke benchmark. No million-token claims.
Uses a user-specified local text corpus. Reports actual server usage if provided.
Run only against the local service with a configured API key.
"""
import argparse
import http.client
import json
import os
from pathlib import Path
import secrets
import time

def main():
    p = argparse.ArgumentParser()
    p.add_argument("corpus", type=Path)
    p.add_argument("--port", type=int, default=18080)
    p.add_argument("--model", default="local-longctx")
    p.add_argument("--position", type=float, default=0.5)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if not 0 <= args.position <= 1:
        p.error("position must be in [0,1]")
    text = args.corpus.read_text(encoding="utf-8")
    secret = secrets.token_hex(8)
    i = int(len(text)*args.position)
    prompt = text[:i] + "\nReference code: " + secret + "\n" + text[i:]
    prompt += "\nReturn only the reference code from the text."
    body = {"model": args.model, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 64, "temperature": 0, "stream": True,
            "stream_options": {"include_usage": True}}
    result = stream_completion(args.port, body)
    answer = result.pop("text")
    result.update(model=args.model, corpus_chars=len(text), needle_character_fraction=args.position,
                  exact_match=answer.strip() == secret,
                  note="Single smoke test; character position is not token position; usage absent means token length unverified.")
    out = json.dumps(result, indent=2)
    print(out)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out+"\n", encoding="utf-8")
    return 0 if result["stream_complete"] and result["exact_match"] else 1

def stream_completion(port, body):
    key = os.environ["LOCAL_LONGCTX_API_KEY"]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=86400)
    start = time.monotonic()
    first = None
    chunks = []
    usage = None
    complete = False
    try:
        conn.request("POST", "/v1/chat/completions", json.dumps(body, ensure_ascii=False).encode(),
                     {"Content-Type": "application/json", "Authorization": "Bearer "+key})
        res = conn.getresponse()
        if res.status != 200:
            raise RuntimeError("benchmark HTTP %d: %s" % (res.status, res.read(4096).decode(errors="replace")))
        for line in res:
            if not line.startswith(b"data:"):
                continue
            data = line[5:].strip()
            if data == b"[DONE]":
                complete = True
                break
            event = json.loads(data)
            if event.get("usage"):
                usage = event["usage"]
            for item in event.get("choices", []):
                part = item.get("delta", {}).get("content")
                if isinstance(part, str) and part:
                    if first is None:
                        first = time.monotonic()
                    chunks.append(part)
    finally:
        conn.close()
    end = time.monotonic()
    return {"stream_complete": complete, "text": "".join(chunks),
            "ttft_seconds": first-start if first is not None else None,
            "elapsed_seconds": end-start, "usage": usage}


if __name__ == "__main__":
    raise SystemExit(main())
