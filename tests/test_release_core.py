"""Release consistency and protocol regressions / 发行一致性与协议回归。"""
import unittest
from pathlib import Path
from types import SimpleNamespace
from longctx import __version__
from longctx.native_messages import validate_prompt
from longctx.planner import RequestError
from longctx.service import reject_constant

class ReleaseCoreTests(unittest.TestCase):
    def test_version(self):
        root=Path(__file__).resolve().parents[1]
        self.assertIn('version = "'+__version__+'"',(root/"pyproject.toml").read_text(encoding="utf-8"))
    def test_invalid_json_constant(self):
        for x in ("NaN","Infinity","-Infinity"):
            with self.assertRaises(ValueError):
                reject_constant(x)
    def test_tools_type(self):
        c=SimpleNamespace(model_id="local-longctx")
        for bad in (False,0,"",{}):
            with self.assertRaises(RequestError):
                validate_prompt({"model":c.model_id,"messages":[{"role":"user","content":"test"}],"tools":bad},c,True)

    def test_backend_json_rejects_invalid_protocol_envelopes_and_closes(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from longctx.backend import Backend, BackendError

        backend = Backend(SimpleNamespace())
        for payload in (b"[]", b"null", b"{", b'{"input_tokens":NaN}', b"\xff"):
            connection = Mock()
            response = Mock(status=200)
            response.read.return_value = payload
            with patch.object(backend, "request", return_value=(connection, response)):
                with self.assertRaises(BackendError):
                    backend.json("/v1/messages/count_tokens")
            connection.close.assert_called_once()
