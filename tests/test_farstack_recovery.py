from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from threading import Lock
import unittest
from unittest.mock import patch

from longctx.backend import BackendError
from longctx.config import Config
from longctx.freetoken import FreeTokenBackend
from longctx.service import Handler, buffer_initial_sse


class FarStackRecoveryTests(unittest.TestCase):
    def test_only_verified_storage_fault_triggers_one_restart(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            model, engine = root / "model.gguf", root / "python.exe"
            model.write_bytes(b"GGUF")
            engine.touch()
            config = Config(engine, model, state_dir=root, experimental_ssd=True,
                            bundled_engine=True, ssd_active_kv=True, kv_tokens=20000)
            backend = FreeTokenBackend(config, None)
            backend.kv_fault_marker = root / "fault"
            with patch.object(backend, "start") as start, patch.object(backend, "close") as close:
                self.assertFalse(backend.recover_tiered_kv())
                start.assert_not_called()
                backend.kv_fault_marker.write_bytes(b"0")
                self.assertFalse(backend.recover_tiered_kv())
                backend.kv_fault_marker.write_bytes(b"1")
                self.assertTrue(backend.recover_tiered_kv())
                self.assertEqual(backend.config, replace(config, ssd_active_kv=False, kv_tokens=0))
                self.assertTrue(backend.kv_recovered)
                self.assertFalse(backend.recover_tiered_kv())
                start.assert_called_once_with(stop_event=None)
                close.assert_called_once_with()

    def test_stream_initial_frames_are_replayed_only_once(self):
        start = b'event: message_start\ndata: {}\n\n'
        with self.assertRaises(BackendError):
            buffer_initial_sse(BytesIO(start + b'event: error\ndata: {}\n\n'))
        good = BytesIO(start + b'event: content_block_start\ndata: {}\n\n')
        self.assertEqual(buffer_initial_sse(good), start + b'event: content_block_start\n')
        self.assertEqual(good.read(), b'data: {}\n\n')

    def test_desktop_prompt_adopts_restart_budget_and_keeps_original(self):
        with TemporaryDirectory() as directory:
            raw = 'word ' * 220
            cfg = SimpleNamespace(model_id='local-longctx', output_reserve=128, state_dir=Path(directory))
            handler = Handler.__new__(Handler)
            backend = SimpleNamespace(budget_window=lambda: 512, json=lambda path, body: {
                'input_tokens': sum(len(m['content'].split()) for m in body['messages'])
            })
            handler.server = SimpleNamespace(config=cfg, backend=backend)
            plan, body = handler.desktop_prompt({
                'model': cfg.model_id, 'max_tokens': 128, 'messages': [{'role': 'user', 'content': raw}]
            }, 'session-1')
            self.assertLessEqual(plan.prompt_tokens + plan.output_tokens + 256, 512)
            self.assertNotEqual(body['messages'][0]['content'], raw)
            from longctx.desktop_history import DesktopHistory
            self.assertEqual(DesktopHistory(Path(directory)).read('session-1', 1)['content'], raw)

    def test_desktop_dispatch_replans_once_after_storage_fault(self):
        with TemporaryDirectory() as directory:
            original = {'model': 'local-longctx', 'max_tokens': 128,
                        'messages': [{'role': 'user', 'content': 'word ' * 220}]}
            raw = json.dumps(original).encode()
            cap = 1024
            sent = []
            replies = []

            def request(path, body):
                sent.append(body)
                response = BytesIO(b'{"content":[]}')
                response.status = 503 if len(sent) == 1 else 200
                response.getheader = lambda name, default: default
                return BytesIO(), response

            def recover():
                nonlocal cap
                cap = 512
                return True

            handler = Handler.__new__(Handler)
            handler.authorized = lambda: True
            handler.reply = lambda status, payload: replies.append((status,payload))
            handler.path = '/v1/messages'
            handler.headers = {'Content-Length': str(len(raw)), 'X-FarStack-Session': 'session-1'}
            handler.headers = SimpleNamespace(get=handler.headers.get, get_content_type=lambda: 'application/json')
            handler.rfile = BytesIO(raw)
            handler.server = SimpleNamespace(
                config=SimpleNamespace(model_id='local-longctx', output_reserve=128, state_dir=Path(directory)),
                active=Lock(), recover_tiered_kv=recover,
                backend=SimpleNamespace(request=request, budget_window=lambda: cap,
                                        json=lambda path, body: {'input_tokens': sum(len(m['content'].split())
                                                                                   for m in body['messages'])}),
            )
            handler.do_POST()
            self.assertEqual(replies, [(200, {'content': []})])
            self.assertEqual(len(sent), 2)
            self.assertEqual(sent[0], original)
            self.assertNotEqual(sent[1]['messages'], original['messages'])
