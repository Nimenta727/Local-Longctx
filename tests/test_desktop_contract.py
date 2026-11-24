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
            p=preview(c,{"context":8192,"threads":2})
            self.assertFalse(p["apply"])
            self.assertEqual(p["settings"]["context"],8192)
            self.assertEqual(c.context,32768)
            for bad in ({"context":1000000},{"model_limit":1000000},{"freetoken_server":"/tmp/other"},{"web_search":True}):
                with self.assertRaises(ValueError):
                    preview(c,bad)
