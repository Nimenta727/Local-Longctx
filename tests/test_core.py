import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from longctx.config import Config,memory_plan
from longctx.scheduler import choose
from longctx.hardware import Hardware,GPU
from longctx.context import Identity,checkpoint,reusable
from longctx.freetoken import command

class TestCore(unittest.TestCase):
    def test_no_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            model=p/"m.gguf"
            model.write_bytes(b"GGUF")
            exe=p/"ft"
            exe.touch()
            c=Config(exe,model,model_is_moe=True,freetoken_model_verified=True).validate()
            hw=Hardware("Linux",8,16,12,300,(GPU("GPU-test","NVIDIA",7,8,"driver"),))
            decision=choose(c,hw)
            self.assertEqual(decision.engine,"freetoken")
            self.assertIn("--kv-cache-dtype",command(c,decision))
            for bad in (replace(hw,nvidia=()),replace(hw,ram_available_gib=None)):
                with self.assertRaises(ValueError):
                    choose(c,bad)
            with self.assertRaises(ValueError):
                choose(replace(c,freetoken_model_verified=False),hw)
            estimate=memory_plan(replace(c,context=1000000,attention_layers=6,kv_heads=2,head_dim=128,kv_cache_dtype="int8_per_token_head"))
            self.assertAlmostEqual(estimate["attention_kv_estimate_gib"],2.95,places=2)
    def test_identity(self):
        i=Identity("freetoken","rev","model","tokenizer","template","schema","auto","rope","session")
        s=checkpoint(i,[1,2,3])
        self.assertTrue(reusable(s,i,[1,2,3,4]))
        self.assertFalse(reusable(s,replace(i,revision="other"),[1,2,3]))
