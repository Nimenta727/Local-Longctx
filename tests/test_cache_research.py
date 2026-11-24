import tempfile
import unittest
from longctx.cache_control import geometry,plan
from longctx.kv_research import pack,unpack,precision
from longctx.tier_research import PageStore

class ResearchTests(unittest.TestCase):
    def test_quant(self):
        values=[-3.,-.2,0.,.9,3.]
        for b in (4,8):
            p=pack(values,b)
            self.assertEqual(len(p.data),(len(values)*b+7)//8)
            self.assertLessEqual(max(abs(x-y) for x,y in zip(values,unpack(p))),p.scale*.501)
        self.assertEqual(precision(.1,.1),4)
        self.assertEqual(precision(.1,.1,True),8)
    def test_tier(self):
        with tempfile.TemporaryDirectory() as d:
            s=PageStore(d,4,12)
            a=s.put(b'abcd');b=s.put(b'efgh')
            self.assertNotIn(a,s.ram)
            self.assertEqual(s.get(a),b'abcd')
            self.assertNotIn(b,s.ram)
            with self.assertRaises(ValueError):s.put(b'12345')
    def test_plan(self):
        g={"pools":{"kv_tokens":{"value":64,"step":16,"min":16,"max":256,"unit_bytes":4,"adjustable":True},
                    "moe_experts":{"value":4,"step":1,"min":2,"max":16,"unit_bytes":32,"adjustable":True},
                    "swa_tokens":{"value":0,"step":0,"min":0,"max":0,"unit_bytes":0,"adjustable":False},
                    "mamba_slots":{"value":0,"step":1,"min":0,"max":0,"unit_bytes":0,"adjustable":False}},"budget_bytes":512}
        self.assertEqual(plan(g,{"kv_tokens":96})["arguments"],{"num_pages":6})
        for draft in ({"kv_tokens":65},{"kv_tokens":128},{"swa_tokens":1},{"moe_experts":17}):
            with self.assertRaises(ValueError):plan(g,draft)
