from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from longctx.desktop_history import DesktopHistory, _text, fit_desktop_prompt
from longctx.native_messages import validate_prompt
from types import SimpleNamespace


class CountingBackend:
    def json(self, path, body):
        assert path == "/v1/messages/count_tokens"
        return {"input_tokens": sum(len(_text(item).split()) + 4 for item in body["messages"])}


class DesktopHistoryTests(unittest.TestCase):
    def test_overflow_preserves_originals_and_replays_complete_tool_groups(self):
        with TemporaryDirectory() as directory:
            history = DesktopHistory(Path(directory))
            original = {"role": "user", "content": "Decision: preserve public API version sapphire.\n" + "archive " * 900}
            latest = [
                {"role": "user", "content": "Find sapphire"},
                {"role": "assistant", "content": [{"type": "tool_use", "id": "c1", "name": "read", "input": {}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "result"}]},
            ]
            prompt = {"model": "local-longctx", "messages": [original, *latest]}
            history.remember("session-a", prompt["messages"])
            messages, count = fit_desktop_prompt(prompt, 32, 400, CountingBackend(), history, "session-a")
            self.assertEqual(messages[-3:], latest)
            self.assertIn("public API", messages[0]["content"])
            self.assertLessEqual(count, 112)
            validate_prompt({**prompt, "messages": messages, "max_tokens": 32}, SimpleNamespace(model_id="local-longctx"))
            self.assertEqual(history.read("session-a", 1), original)
            self.assertIsNone(history.read("session-b", 1))

    def test_large_single_message_is_saved_before_reducing_projection(self):
        with TemporaryDirectory() as directory:
            history = DesktopHistory(Path(directory))
            original = {"role": "user", "content": "start " + "word " * 100000 + "end"}
            history.remember("session-a", [original])
            messages, count = fit_desktop_prompt({"model":"local-longctx","messages":[original]},
                                                  32, 400, CountingBackend(), history, "session-a")
            self.assertLessEqual(count, 112)
            self.assertIn("Full content retained", messages[-1]["content"])
            self.assertEqual(DesktopHistory(Path(directory)).read("session-a", 1), original)
