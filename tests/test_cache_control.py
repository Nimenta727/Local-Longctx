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
