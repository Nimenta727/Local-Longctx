import json
import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from benchmarks.context_baseline import (
    CASES, MARGIN, VARIANTS, NativeGateway, OfflineCounter, evaluate_case, summary,
)


class ContextBaselineTests(unittest.TestCase):
    def test_fixed_cases_preserve_budget_and_recall_cross_language_evidence(self):
        args = SimpleNamespace(window=2048, output_tokens=128, recall_tokens=320,
                               history_scale=1, live=False)
        with TemporaryDirectory() as directory:
            cases = {case: evaluate_case(case, args, OfflineCounter(), directory, VARIANTS)
                     for case in CASES}
        limited_budget = args.window - args.output_tokens - MARGIN
        for rows in cases.values():
            for name in ("sliding", "managed"):
                self.assertLessEqual(rows[name]["input_units"], limited_budget)
                self.assertNotIn("task_pass", rows[name])
            self.assertLessEqual(rows["managed"]["recall_units"], args.recall_tokens)
        totals = summary(cases)
        self.assertEqual(totals["full"]["evidence_found"], 9)
        self.assertEqual(totals["managed"]["evidence_found"], 9)
        self.assertEqual(totals["sliding"]["evidence_found"], 0)
        self.assertTrue(cases["paraphrased_evidence"]["managed"]["evidence"]["backup"])
        self.assertGreater(cases["tool_evidence"]["managed"]["recall_units"], 0)

    def test_live_reader_scores_only_completed_native_stream(self):
        gateway = NativeGateway(18080, "local-longctx", "test")
        messages = [{"role": "system", "content": "Return JSON."},
                    {"role": "user", "content": "What is the result?"}]
        events = [
            {"type": "message_start", "message": {"usage": {"input_tokens": 48}}},
            {"type": "content_block_start", "content_block": {"type": "text", "text": '{"id":'}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": '"R7"}'}},
            {"type": "message_delta", "usage": {"output_tokens": 8}},
            {"type": "message_stop"},
        ]

        def sample(_port, _stop, pages):
            pages.extend((2, 5))

        with patch("benchmarks.context_baseline.http.client.HTTPConnection"), \
                patch("benchmarks.context_baseline.sample_kv", side_effect=sample), \
                patch.object(gateway, "request") as request:
            request.return_value = [b"data: " + json.dumps(event).encode() + b"\n" for event in events]
            answer, metrics = gateway.answer(messages, 128)
            self.assertEqual(answer, {"id": "R7"})
            self.assertEqual(metrics["usage"], {"input_tokens": 48, "output_tokens": 8})
            self.assertEqual(metrics["sampled_peak_kv_pages"], 5)
            self.assertIsNotNone(metrics["ttft_seconds"])
            request.return_value = request.return_value[:-1]
            answer, metrics = gateway.answer(messages, 128)
            self.assertIsNone(answer)
            self.assertFalse(metrics["stream_complete"])
