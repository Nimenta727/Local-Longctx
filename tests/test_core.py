import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from longctx.config import Config, memory_plan
from longctx.backend import command
from longctx.planner import prepare, RequestError
from longctx.openclaw import configuration

class FakeBackend:
    def __init__(self, count):
        self.count = count
    def json(self, path, data=None):
        if path == "/apply-template":
            return {"prompt": "rendered"}
        if path == "/tokenize":
            return {"tokens": [1] * self.count}
        raise AssertionError(path)

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        model = root / "test.gguf"
        model.write_bytes(b"GGUF")
        server = root / "llama-server"
        server.touch()
        self.c = Config(server=server, model=model, context=1000,
                        model_limit=1000, output_reserve=100,
                        batch=128, ubatch=64, attention_layers=6,
                        kv_heads=2, head_dim=128).validate()
        self.body = {"model": self.c.model_id,
                     "messages": [{"role": "user", "content": "hello"}]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan(self):
        p, b = prepare(self.body, self.c, FakeBackend(800))
        self.assertEqual(p.prompt_tokens, 800)
        self.assertEqual(b["max_tokens"], 100)
        self.assertEqual(p.mode, "full")

    def test_overflow(self):
        with self.assertRaises(RequestError):
            prepare(self.body, self.c, FakeBackend(900))

    def test_no_tools_or_override(self):
        for extra in ({"tools": [{"type": "function"}]}, {"truncate": True},
                      {"max_tokens": 101}, {"max_tokens": 10, "max_completion_tokens": 11}):
            with self.subTest(extra=extra), self.assertRaises(RequestError):
                prepare({**self.body, **extra}, self.c, FakeBackend(1))

    def test_model_mismatch(self):
        with self.assertRaises(RequestError):
            prepare({**self.body, "model": "remote"}, self.c, FakeBackend(1))

    def test_command(self):
        args = command(self.c)
        self.assertIn("--no-context-shift", args)
        self.assertIn("--no-kv-offload", args)
        self.assertEqual(args[args.index("--parallel")+1], "1")
        self.assertEqual(args[args.index("--host")+1], "127.0.0.1")

    def test_config(self):
        with self.assertRaises(ValueError):
            replace(self.c, context=1001).validate()
        with self.assertRaises(ValueError):
            replace(self.c, api_port=self.c.backend_port).validate()

    def test_memory(self):
        p = memory_plan(replace(self.c, context=1000000, cache_type="q8_0"))
        self.assertAlmostEqual(p["attention_kv_gib"], 3.04, places=2)
        self.assertEqual(p["mode"], "compressed")

    def test_openclaw_isolation(self):
        cfg = configuration(self.c, "api-ref", "gateway-ref")
        self.assertEqual(cfg["gateway"]["bind"], "loopback")
        self.assertEqual(cfg["tools"]["deny"], ["*"])
        self.assertEqual(cfg["agents"]["defaults"]["model"]["fallbacks"], [])
        self.assertEqual(cfg["models"]["mode"], "replace")

if __name__ == "__main__":
    unittest.main()
