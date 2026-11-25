"""Replay fixed long-history tasks through the native gateway or inspect evidence offline."""
import argparse
import http.client
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import monotonic
from types import SimpleNamespace

from benchmarks.managed_replay import sample_kv
from longctx import __version__
from longctx.managed import compact_session, recall_prompt
from longctx.session_store import Store
from longctx.telemetry import Metrics

SYSTEM = "Continue the task using the conversation. Return one JSON object. Use null for unknown values."
VARIANTS = ("full", "sliding", "managed")
MARGIN = 256
# Prompts name the needed fields or evidence sources without including the answers.
CASES = {
    "early_constraints": (
        [("constraint", "Required compatibility", "legacy-v17"),
         ("decision", "Approved deployment region", "north-03")],
        "What compatibility value is required and what region was approved?",
        ("compatibility", "region"),
    ),
    "failed_attempt": (
        [("failed_attempt", "Rejected rollout", "swap-amber"),
         ("failed_attempt", "Rejected because", "stale-lock-42")],
        "Which rollout should we avoid repeating, and why?",
        ("rollout", "failure"),
    ),
    "tool_evidence": (
        [(None, "render_manifest.py ERR_381 result", "run-id-6J9")],
        "Find the run ID in the render_manifest.py ERR_381 tool result.",
        ("run_id",),
    ),
    "distributed_evidence": (
        [(None, "importer.py E213 observed", "batch-K72"),
         (None, "writer.py E304 observed", "batch-P91"),
         (None, "validator.py E155 observed", "batch-X38")],
        "Compare importer.py E213, writer.py E304, and validator.py E155. Which batch did each observe?",
        ("importer", "writer", "validator"),
    ),
    "paraphrased_evidence": (
        [(None, "数据库恢复流程指定了此备份", "snapshot-M61")],
        "Which backup should I use to bring the database back?",
        ("backup",),
    ),
}


def message(role, content):
    return {"role": role, "content": content}


def scenario(case, history_scale):
    facts, question, keys = CASES[case]
    history = [message("system", SYSTEM)]
    segments = []
    for turn in range(max(3, len(facts))):
        history.append(message("user", f"Record verification checkpoint {turn + 1}."))
        lines = [f"Checkpoint {turn + 1} observation {i:04d}: routine verification completed."
                 for i in range(120 * history_scale)]
        state = []
        if turn < len(facts):
            kind, clue, value = facts[turn]
            entry = f"Source verification observation: {clue}: {value}. Archive reference validated independently."
            lines.insert(len(lines) // 2, entry)
            if kind is not None:
                state.append({"kind": kind, "quote": entry})
        segments.append({"index": len(history), "pinned": False, "anchors": [],
                         "budget_chars": 360, "importance": .1, "access_frequency": .1,
                         "dependency": .1, "task_state": state})
        history.append(message("assistant", "\n".join(lines)))
    for turn in range(5):
        follow_up = "\n".join(f"Follow-up {turn + 1}.{i + 1:02d} confirmed routine status."
                              for i in range(12))
        history.extend([message("user", f"Summarize routine follow-up {turn + 1}."),
                        message("assistant", follow_up)])
    query = question + " Use these JSON keys: " + ", ".join(keys) + "."
    expected = dict(zip(keys, (value for _, _, value in facts)))
    return history, segments, query, expected


class OfflineCounter:
    def count_prompt(self, messages):
        return sum(4 + (len(m["content"].encode("utf-8")) + 3) // 4 for m in messages)


class NativeGateway:
    def __init__(self, port, model, key):
        self.port = port
        self.model = model
        self.headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json",
                        "anthropic-version": "2023-06-01"}

    def payload(self, messages):
        return {"model": self.model, "system": messages[0]["content"], "messages": messages[1:]}

    def request(self, connection, path, body):
        connection.request("POST", path, json.dumps(body, ensure_ascii=False).encode(), self.headers)
        response = connection.getresponse()
        if response.status != 200:
            detail = response.read(1024).decode(errors="replace")
            raise ValueError(f"{path} HTTP {response.status}: {detail}")
        return response

    def count_prompt(self, messages):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            return json.load(self.request(connection, "/v1/messages/count_tokens",
                                          self.payload(messages)))["input_tokens"]
        finally:
            connection.close()

    def answer(self, messages, max_tokens):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=180)
        stop, pages = Event(), []
        sampler = Thread(target=sample_kv, args=(self.port, stop, pages))
        chunks, usage, first, complete = [], {}, None, False
        payload = dict(self.payload(messages), max_tokens=max_tokens, stream=True, temperature=0)
        sampler.start()
        start = monotonic()
        try:
            response = self.request(connection, "/v1/messages", payload)
            for line in response:
                if not line.startswith(b"data:"):
                    continue
                event = json.loads(line[5:])
                kind = event.get("type")
                if kind == "message_stop":
                    complete = True
                    break
                if kind == "error":
                    break
                if kind == "message_start":
                    usage.update(event.get("message", {}).get("usage", {}))
                elif kind == "message_delta":
                    usage.update(event.get("usage", {}))
                elif kind == "content_block_start" and event["content_block"].get("type") == "text":
                    text = event["content_block"].get("text", "")
                    if text:
                        first = first if first is not None else monotonic()
                        chunks.append(text)
                elif kind == "content_block_delta" and event["delta"].get("type") == "text_delta":
                    text = event["delta"].get("text", "")
                    if text:
                        first = first if first is not None else monotonic()
                        chunks.append(text)
            elapsed = monotonic() - start
        finally:
            connection.close()
            stop.set()
            sampler.join()
        try:
            parsed = json.loads("".join(chunks)) if complete else None
        except ValueError:
            parsed = None
        return parsed, {"stream_complete": complete, "ttft_seconds": None if first is None else first - start,
                        "elapsed_seconds": elapsed, "usage": usage, "kv_samples": len(pages),
                        "sampled_peak_kv_pages": max(pages, default=None)}


def sliding_prompt(history, query, counter, budget):
    end = message("user", query)
    # The source histories consist of a system head and complete user/assistant pairs.
    for start in range(1, len(history) + 1, 2):
        prompt = [history[0], *history[start:], end]
        if counter.count_prompt(prompt) <= budget:
            return prompt
    raise ValueError("final request alone exceeds the shared input budget")


def managed_prompt(case, history, segments, query, counter, config, recall_budget, state_dir):
    store = Store(state_dir)
    original = store.create(case, history, True)
    report = compact_session(store, counter, config, {
        "session": case, "expected_revision": original["revision"], "expected_sha": original["sha256"],
        "commit": True, "telemetry_profile": {}, "segments": segments,
        "estimates": {"growth_tokens_per_second": 0, "history_dependency": .1, "compact_seconds": 0,
                      "expected_turns": 8, "prefix_recompute_tokens": 0, "cache_hit_fraction": 0,
                      "seconds_since_compact": 600, "compact_peak_ram_gib": 0, "compact_peak_vram_gib": 0},
    }, sampler=lambda *_: Metrics(8, 16, 4, 8, 0, 200, 0))
    if not report.get("committed") and report.get("decision", {}).get("action") != "keep":
        raise ValueError(str(report.get("decision", {}).get("reasons", "compaction unavailable")))
    return recall_prompt(store, counter, config, {
        "session": case, "query": query, "max_recall_tokens": recall_budget,
    })


def evidence_checks(prompt, expected):
    return {key: any(value in m["content"] for m in prompt) for key, value in expected.items()}


def evaluate_case(case, args, counter, state_dir, order):
    config = SimpleNamespace(context=args.window, output_reserve=args.output_tokens)
    history, segments, query, expected = scenario(case, args.history_scale)
    full = [*history, message("user", query)]
    input_budget = args.window - args.output_tokens - MARGIN
    results = {}
    for variant in order:
        try:
            if variant == "full":
                prompt = full
            elif variant == "sliding":
                prompt = sliding_prompt(history, query, counter, input_budget)
            else:
                recalled = managed_prompt(case, history, segments, query, counter, config,
                                          args.recall_tokens, state_dir)
                prompt = recalled["messages"]
            units = counter.count_prompt(prompt)
            row = {"input_units": units, "evidence": evidence_checks(prompt, expected)}
            if variant == "managed":
                row["recall_units"] = recalled["recall_tokens"]
            if args.live and units > args.engine_window - args.output_tokens - MARGIN:
                row["inference_skipped"] = "exceeds configured engine window"
            elif args.live:
                try:
                    answer, metrics = counter.answer(prompt, args.output_tokens)
                    checks = {key: isinstance(answer, dict) and answer.get(key) == value
                              for key, value in expected.items()}
                    row.update(metrics, checks=checks, task_pass=all(checks.values()))
                except (OSError, ValueError, http.client.HTTPException) as exc:
                    row["inference_error"] = str(exc)
            results[variant] = row
        except (OSError, ValueError, KeyError, http.client.HTTPException) as exc:
            results[variant] = {"preparation_error": str(exc)}
    return results


def summary(cases):
    result = {}
    expected_fields = sum(len(CASES[case][2]) for case in cases)
    for variant in VARIANTS:
        rows = [case[variant] for case in cases.values()]
        evidence = [value for row in rows for value in row.get("evidence", {}).values()]
        tried = [row["task_pass"] for row in rows if "task_pass" in row]
        result[variant] = {"prepared_cases": sum("evidence" in row for row in rows),
                           "evidence_found": sum(evidence), "evidence_total": expected_fields,
                           "scored_tasks": len(tried), "passed_tasks": sum(tried)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--model", default="local-longctx")
    parser.add_argument("--window", type=int, default=2048, help="shared input/output window for limited variants")
    parser.add_argument("--engine-window", type=int, help="actual gateway window, required with --live")
    parser.add_argument("--output-tokens", type=int, default=128)
    parser.add_argument("--recall-tokens", type=int, default=320)
    parser.add_argument("--history-scale", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if (args.history_scale < 1 or args.output_tokens < 1 or args.window <= args.output_tokens + MARGIN
            or not 0 <= args.recall_tokens <= args.window):
        parser.error("invalid history or budget")
    if args.live and (args.engine_window is None or args.engine_window < args.window):
        parser.error("--live requires --engine-window at least as large as --window")
    key = os.environ.get("LOCAL_LONGCTX_API_KEY") if args.live else None
    if args.live and not key:
        parser.error("LOCAL_LONGCTX_API_KEY is required with --live")
    counter = NativeGateway(args.port, args.model, key) if args.live else OfflineCounter()
    with TemporaryDirectory() as directory:
        cases = {}
        for index, case in enumerate(CASES):
            offset = index % len(VARIANTS)
            order = VARIANTS[offset:] + VARIANTS[:offset]
            cases[case] = evaluate_case(case, args, counter, directory, order)
    report = {"version": __version__, "path": "managed-session-api",
              "counting": "native_messages_tokens" if args.live else "approximate_utf8_units",
              "model": args.model if args.live else None, "window": args.window,
              "engine_window": args.engine_window, "output_tokens": args.output_tokens,
              "recall_budget": args.recall_tokens, "history_scale": args.history_scale,
              "cases": cases, "summary": summary(cases)}
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    return int(any("preparation_error" in row or "inference_error" in row
                   for case in cases.values() for row in case.values())
               or (args.live and not report["summary"]["full"]["scored_tasks"]))


if __name__ == "__main__":
    raise SystemExit(main())
