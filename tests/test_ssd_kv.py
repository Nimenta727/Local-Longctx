from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from longctx.config import Config
from longctx.freetoken import command
from longctx.freetoken_ssd_kv import DIGEST_BYTES, HEADER, SSDPrefixCheckpoint


class SSDKVTests(unittest.TestCase):
    def test_launch_is_explicit(self):
        config = Config(Path("/engine/ft"), Path("/model.gguf"), state_dir=Path("/local/state"))
        decision = SimpleNamespace(gpu_uuid="GPU-0", prefill_chunk=512, memory_ratio=.8, threads=4)
        regular = command(config, decision)
        self.assertNotIn("--experimental-ssd-kv", regular)
        self.assertEqual(command(replace(config, ssd_kv_checkpoint=True), decision), regular)
        self.assertEqual(command(replace(config, experimental_ssd=True), decision), regular)
        enabled = replace(config, experimental_ssd=True, ssd_kv_checkpoint=True, ssd_kv_limit_mib=512)
        self.assertEqual(command(enabled, decision),
                         regular + ["--experimental-ssd-kv",
                                    str((config.state_dir / "runtime-cache" / "ssd-kv.bin").resolve()),
                                    "--experimental-ssd-kv-limit-mib", "512"])
        with TemporaryDirectory() as directory:
            model = Path(directory) / "model.gguf"
            model.write_bytes(b"GGUF")
            native = SimpleNamespace(model_path=str(model), experimental_ssd_kv=str(model))
            with self.assertRaisesRegex(ValueError, "different from the model file"):
                SSDPrefixCheckpoint.from_engine(native, None)

    def test_restart_round_trip_and_failed_restore_leave_radix_untouched(self):
        try:
            import torch
        except ImportError:
            self.skipTest("PyTorch is needed to exercise the KV checkpoint")

        def pool(data):
            return SimpleNamespace(_kv_buffer=data, _scale_buffer=None,
                                   unit_bytes=lambda: (32, 0))

        def manager():
            return SimpleNamespace(free_slots=torch.tensor([0, 1, 2, 5]),
                                   _allocate=Mock(return_value=torch.tensor([0, 1, 2])),
                                   _free=Mock(),
                                   prefix_cache=SimpleNamespace(insert_prefix=Mock(return_value=(0, None))))

        data = torch.arange(2 * 2 * 6 * 4, dtype=torch.float32).to(torch.bfloat16).view(2, 2, 6, 1, 1, 4)
        ids = torch.tensor([10, 20, 30, 40, 50], dtype=torch.int32)
        source_indices = torch.tensor([5, 3, 1, 0, 4])
        cap = HEADER.size + 3 * 32 + DIGEST_BYTES
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ssd-kv.bin"
            SSDPrefixCheckpoint(path, pool(data), "model-a", cap).save(ids, source_indices)
            self.assertEqual(path.stat().st_size, cap)
            original = path.read_bytes()
            target = torch.zeros_like(data)
            checkpoint = SSDPrefixCheckpoint(path, pool(target), "model-a", cap)
            cache = manager()
            self.assertFalse(SSDPrefixCheckpoint(path, pool(target), "model-b", cap).restore(ids, cache, 0))
            self.assertFalse(checkpoint.restore(torch.tensor([10, 21, 30]), cache, 0))
            self.assertFalse(checkpoint.restore(ids[:2], cache, 0))
            self.assertFalse(checkpoint.restore(ids, cache, 3))
            cache._allocate.assert_not_called()

            self.assertTrue(checkpoint.restore(ids, cache, 0))
            torch.testing.assert_close(target[:, :, :3], data.index_select(2, source_indices[:3]))
            tree_ids, tree_slots = cache.prefix_cache.insert_prefix.call_args.args
            torch.testing.assert_close(tree_ids, ids[:3])
            torch.testing.assert_close(tree_slots, torch.arange(3))

            corrupt = bytearray(original)
            corrupt[HEADER.size] ^= 1
            path.write_bytes(corrupt)
            cache = manager()
            with self.assertLogs("longctx.freetoken_ssd_kv", level="WARNING"):
                self.assertFalse(checkpoint.restore(ids, cache, 0))
            cache.prefix_cache.insert_prefix.assert_not_called()
            torch.testing.assert_close(cache._free.call_args.args[0], torch.arange(3))
            target[:, :, :3].copy_(data.index_select(2, source_indices[:3]))
            checkpoint.save(ids, torch.arange(3))
            self.assertEqual(path.read_bytes(), original)
            checkpoint.clear()
            self.assertFalse(path.exists())
