import unittest
from dataclasses import replace
from longctx.compact import Snapshot,Segment,evaluate

class TestCompact(unittest.TestCase):
    def setUp(self):
        self.s=Snapshot(3,16,1.4,8,29000,32768,1024,50,.89,.3,500,3,8,4000,
                        exact_mode=False,allow_semantic=True,cache_hit_fraction=.2)
        self.segments=[Segment("old",12000,.1,.1,.1,1000),
                       Segment("pinned",4000,.1,.1,.1,0,pinned=True)]
    def test_proposal(self):
        d=evaluate(self.s,self.segments)
        self.assertEqual(d.action,"propose_semantic_compact")
        self.assertEqual(d.candidates,("old",))
        self.assertEqual(d.estimated_saved_tokens,11000)
    def test_exact(self):
        self.assertNotEqual(evaluate(replace(self.s,exact_mode=True),self.segments).action,"propose_semantic_compact")
    def test_no_consent(self):
        self.assertNotEqual(evaluate(replace(self.s,allow_semantic=False),self.segments).action,"propose_semantic_compact")
    def test_active(self):
        self.assertEqual(evaluate(replace(self.s,idle=False),self.segments).action,"defer")
    def test_cost(self):
        self.assertEqual(evaluate(replace(self.s,cache_hit_fraction=1),self.segments).action,"keep")
    def test_dependency(self):
        self.assertEqual(evaluate(replace(self.s,history_dependency=.9),self.segments).action,"keep")
    def test_growth(self):
        s=replace(self.s,ram_free_gib=12,vram_free_gib=6,context_tokens=16000,
                  kv_occupancy=.4,growth_tokens_per_second=500)
        self.assertEqual(evaluate(s,self.segments).action,"propose_semantic_compact")
    def test_workspace(self):
        self.assertEqual(evaluate(replace(self.s,compact_peak_vram_gib=2),self.segments).action,"pause_or_native_reclaim")
    def test_invalid(self):
        with self.assertRaises(ValueError):
            evaluate(replace(self.s,kv_occupancy=float("nan")),self.segments)
