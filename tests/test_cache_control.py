"""Cache budget regressions / 缓存预算回归测试。"""
import unittest
from longctx.cache_control import plan,geometry

class CacheTests(unittest.TestCase):
    def test_plan(self):
        g={"pools":{"kv_tokens":{"value":64,"step":16,"min":16,"max":256,"unit_bytes":4,"adjustable":True},
                    "moe_experts":{"value":4,"step":1,"min":2,"max":16,"unit_bytes":32,"adjustable":True},
                    "swa_tokens":{"value":0,"step":0,"min":0,"max":0,"unit_bytes":0,"adjustable":False},
                    "mamba_slots":{"value":0,"step":1,"min":0,"max":0,"unit_bytes":0,"adjustable":False}},"budget_bytes":512}
        self.assertEqual(plan(g,{"kv_tokens":96})["arguments"],{"num_pages":6})
        for draft in ({"kv_tokens":65},{"kv_tokens":128},{"swa_tokens":1},{"moe_experts":17},{"kv_tokens":True}):
            with self.assertRaises(ValueError):
                plan(g,draft)
    def test_unavailable(self):
        with self.assertRaises(ValueError):
            geometry({"state":"rebuilding"})

    def test_saved_capacity_is_restored_only_for_compatible_profile(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from longctx.cache_profile import profile_path, restore, save

        with TemporaryDirectory() as directory:
            state = Path(directory)
            model, engine = state / "model.gguf", state / "ft"
            model.write_bytes(b"model")
            engine.write_bytes(b"engine")
            config = SimpleNamespace(model=model, freetoken_server=engine, state_dir=state,
                                     context=8192, output_reserve=1024, ubatch=512,
                                     kv_cache_dtype="auto", freetoken_memory_ratio=.8,
                                     kv_tokens=0, expert_slots=0)
            backend = Mock()
            backend.decision.gpu_uuid = "gpu"
            backend.json.return_value = {"status": "ok"}
            pools = {name: {"value": 0} for name in ("moe_experts", "swa_tokens", "mamba_slots")}
            for pool in pools.values():
                pool["unit_bytes"] = 0
            pools["kv_tokens"] = {"value": 64, "step": 16, "min": 16, "max": 256,
                                  "unit_bytes": 4, "adjustable": True}
            geometry = {"pools": pools, "budget_bytes": 512, "active_requests": 0}
            save(backend, config, {"kv_tokens": 96})
            restored_geometry = {**geometry, "pools": {
                **pools, "kv_tokens": {**pools["kv_tokens"], "value": 96},
            }}
            with patch("longctx.cache_profile.snapshot", side_effect=[geometry, restored_geometry]):
                self.assertEqual(restore(backend, config), "restored")
                backend.json.assert_called_once_with(
                    "/v1/cache/rebuild", {"num_pages": 6, "mode": "if_idle", "timeout": 300},
                    timeout=310,
                )
                backend.json.reset_mock()
            with patch("longctx.cache_profile.snapshot", return_value=geometry):
                # The engine can say OK without actually landing the requested value.
                self.assertEqual(restore(backend, config), "unavailable")
                backend.json.assert_called_once()
                backend.json.reset_mock()
                geometry["budget_bytes"] = 256
                self.assertEqual(restore(backend, config), "unavailable")
                backend.json.assert_not_called()
                backend.decision.gpu_uuid = "different"
                self.assertEqual(restore(backend, config), "default")
                backend.json.assert_not_called()

            backend.decision.gpu_uuid = "gpu"
            path = profile_path(backend, config)
            for damaged in ("{", "null", '{"kv_tokens":64.0}'):
                path.write_text(damaged, encoding="utf-8")
                backend.json.reset_mock()
                self.assertEqual(restore(backend, config), "unavailable")
                backend.json.assert_not_called()
                save(backend, config, {"kv_tokens": 96})
                with patch("longctx.cache_profile.snapshot", return_value=restored_geometry):
                    self.assertEqual(restore(backend, config), "restored")
                backend.json.assert_not_called()
