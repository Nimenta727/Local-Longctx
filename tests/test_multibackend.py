import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from longctx.config import Config
from longctx.hardware import Hardware,GPU
from longctx.scheduler import choose
from longctx.context import Identity,checkpoint,reusable,check_budget
from longctx.freetoken import command

class MultiBackendTests(unittest.TestCase):
    def test_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            model=p/"m.gguf"
            model.write_bytes(b"GGUF")
            exe=p/"bin"
            exe.touch()
            c=Config(server=exe,model=model,engine="auto",freetoken_server=exe,
                     model_is_moe=True,freetoken_model_verified=True).validate()
            hw=Hardware("Linux",8,64,48,300,(GPU("GPU-test","NVIDIA",12,16,"driver"),))
            d=choose(c,hw)
            self.assertEqual(d.engine,"freetoken")
            self.assertIn("--kv-reserve-tokens",command(c,d))
            self.assertEqual(choose(c,replace(hw,nvidia=())).engine,"llama")
            self.assertEqual(choose(replace(c,freetoken_model_verified=False),hw).engine,"llama")
            with self.assertRaises(ValueError):
                choose(replace(c,engine="freetoken"),replace(hw,nvidia=()))

    def test_state_identity(self):
        i=Identity("llama","rev","model","tokenizer","template","schema","f16","rope","session")
        s=checkpoint(i,[1,2,3])
        self.assertTrue(reusable(s,i,[1,2,3,4]))
        self.assertFalse(reusable(s,i,[1,2,9]))
        self.assertFalse(reusable(s,replace(i,engine="freetoken"),[1,2,3]))

    def test_budget(self):
        check_budget(800,100,1000)
        with self.assertRaises(ValueError):
            check_budget(900,100,1000)
