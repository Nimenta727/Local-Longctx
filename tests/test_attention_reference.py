import math
import random
import unittest
from longctx.attention_reference import streaming_attention,page_bounds,upper_bound,select_pages,dot

class AttentionReferenceTests(unittest.TestCase):
    def test_equivalence(self):
        rng=random.Random(44)
        q=[rng.uniform(-10,10) for _ in range(8)]
        k=[[rng.uniform(-20,20) for _ in q] for _ in range(97)]
        v=[[rng.uniform(-2,2) for _ in range(5)] for _ in k]
        logits=[dot(q,x)/math.sqrt(len(q)) for x in k]
        w=[math.exp(x-max(logits)) for x in logits]
        want=[math.fsum(a*b[j] for a,b in zip(w,v))/math.fsum(w) for j in range(5)]
        for chunk in (1,7,32,97):
            got=streaming_attention(q,((k[i:i+chunk],v[i:i+chunk]) for i in range(0,len(k),chunk)))
            for a,b in zip(want,got):
                self.assertAlmostEqual(a,b,places=12)
    def test_bounds_and_pins(self):
        q=[2.,-3.]
        pages=[[[0.,1.],[2.,4.]],[[8.,-4.]],[[1.,2.]]]
        bounds=[page_bounds(k) for k in pages]
        for page,box in zip(pages,bounds):
            self.assertGreaterEqual(upper_bound(q,box)+1e-12,max(dot(q,k)/math.sqrt(2) for k in page))
        self.assertEqual(select_pages(q,bounds,2,[2]),[1,2])
    def test_invalid(self):
        with self.assertRaises(ValueError):
            streaming_attention([1.],[])
        with self.assertRaises(ValueError):
            select_pages([1.],[([0.],[1.])],1,[2])
