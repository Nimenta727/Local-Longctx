import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from longctx.config import Config
from longctx.desktop_contract import describe,preview

class DesktopContractTests(unittest.TestCase):
    def test_preview_and_truthful_capabilities(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            exe=root/"ft"
            exe.touch()
            model=root/"model.gguf"
            model.write_bytes(b"GGUF")
            c=Config(exe,model).validate()
            out=describe(c)
            self.assertEqual(out["context"]["product_target"],1000000)
            self.assertFalse(out["context"]["native_million_verified"])
            self.assertFalse(out["capabilities"]["web_search"]["enabled"])
            self.assertEqual(out["capabilities"]["image_input"]["status"],"not_integrated")
            self.assertFalse(out["memory_controls"]["ssd_kv_offload"])
            self.assertFalse(out["memory_controls"]["experimental_ssd"])
            self.assertFalse(out["settings"]["ssd_kv_checkpoint"])
            self.assertFalse(out["memory_controls"]["ssd_expert_offload"])
            self.assertFalse(out["settings"]["ssd_expert_offload"])
            self.assertIn("moe_experts",out["memory_controls"]["apply_while_idle"])
            p=preview(c,{"context":8192,"threads":2,"moe_strategy":"offload","host_weights_gib":18})
            self.assertFalse(p["apply"])
            self.assertEqual(p["settings"]["context"],8192)
            self.assertEqual(c.context,32768)
            self.assertEqual(p["settings"]["moe_strategy"],"offload")
            self.assertEqual(p["settings"]["host_weights_gib"],18)
            self.assertTrue(preview(c,{"ssd_kv_checkpoint":True})["settings"]["ssd_kv_checkpoint"])
            self.assertFalse(describe(Config(exe,model,ssd_kv_checkpoint=True))["memory_controls"]["ssd_kv_checkpoint"])
            self.assertTrue(describe(Config(exe,model,experimental_ssd=True,
                                            ssd_kv_checkpoint=True))["memory_controls"]["ssd_kv_checkpoint"])
            for bad in ({"context":1000000},{"model_limit":1000000},{"freetoken_server":"/tmp/other"},{"web_search":True},
                        {"experimental_ssd":True,"ssd_expert_offload":True},
                        {"ssd_expert_offload":"true","moe_strategy":"offload"},
                        {"experimental_ssd":True,"ssd_kv_checkpoint":True,"kv_cache_dtype":"int8_per_token_head"},
                        {"ssd_kv_checkpoint":1},{"ssd_kv_limit_mib":1025},{"ssd_expert_staging_mib":3}):
                with self.assertRaises(ValueError):
                    preview(c,bad)
