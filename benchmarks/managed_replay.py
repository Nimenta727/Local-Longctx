"""Compare three prepared prompt variants against a local FreeToken gateway."""
import argparse
import http.client
import json
import os
from pathlib import Path
from threading import Event, Thread

if __package__:
    from .needle import stream_completion
else:
    from needle import stream_completion


def sample_kv(port, stop, readings):
    headers = {"Authorization": "Bearer " + os.environ["LOCAL_LONGCTX_API_KEY"]}
    while not stop.is_set():
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("GET", "/local/cache/status", headers=headers)
            response = conn.getresponse()
            if response.status == 200:
                used = json.load(response).get("kv_usage", {}).get("used_pages")
                if type(used) is int and used >= 0:
                    readings.append(used)
        except (OSError, ValueError, AttributeError, http.client.HTTPException):
            pass
        finally:
            conn.close()
        stop.wait(.25)


def run(port, model, messages, expected, output_tokens):
    stop = Event()
    readings = []
    sampler = Thread(target=sample_kv, args=(port, stop, readings))
    sampler.start()
    try:
        result = stream_completion(port, {
            "model": model, "messages": messages, "max_tokens": output_tokens,
            "temperature": 0, "stream": True, "stream_options": {"include_usage": True},
        })
    finally:
        stop.set()
        sampler.join()
    try:
        answer = json.loads(result.pop("text"))
    except ValueError:
        answer = None
    result["checks"] = {
        key: result["stream_complete"] and isinstance(answer, dict)
        and key in answer and answer[key] == value
        for key, value in expected.items()
    }
    result["sampled_peak_kv_pages"] = max(readings, default=None)
    result["kv_samples"] = len(readings)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--model", default="local-longctx")
    parser.add_argument("--output-tokens", type=int, default=128)
    parser.add_argument("--order", nargs=3, default=["full", "extract", "recall"],
                        choices=["full", "extract", "recall"])
    parser.add_argument("--warm-prefix", action="store_true",
                        help="replay the common full-history prefix before each measured request")
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    if len(set(args.order)) != 3:
        parser.error("--order must include each variant once")
    results = {}
    for label in args.order:
        if args.warm_prefix:
            warmup = stream_completion(args.port, {
                "model": args.model, "messages": fixture["full"][:-1],
                "max_tokens": 1, "temperature": 0, "stream": True,
            })
            if not warmup["stream_complete"]:
                raise RuntimeError("warmup stream did not complete")
        results[label] = run(args.port, args.model, fixture[label], fixture["expected"], args.output_tokens)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
