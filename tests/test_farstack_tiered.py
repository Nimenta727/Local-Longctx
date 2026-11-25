from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class TieredKVTests(unittest.TestCase):
    def test_mixed_gpu_ram_and_disk_slots_match_dense_causal_attention(self):
        try:
            import torch
            from freetoken.distributed import set_tp_info
            from freetoken.kvcache.farstack_tiered import TieredMHAKVCache, tiered_attention
        except ImportError as exc:
            self.skipTest(f"requires the vendored FreeToken runtime and PyTorch: {exc}")
        set_tp_info(0, 1)
        generator = torch.Generator().manual_seed(19)
        q = torch.randn(3, 4, 4, generator=generator).bfloat16()
        k = torch.randn(6, 2, 4, generator=generator).bfloat16()
        v = torch.randn(6, 2, 4, generator=generator).bfloat16()
        with TemporaryDirectory() as directory:
            config = SimpleNamespace(model_config=SimpleNamespace(num_kv_heads=2, num_layers=1, head_dim=4),
                                     farstack_kv_gpu_tokens=2, farstack_kv_ram_mib=0,
                                     farstack_kv_dir=Path(directory))
            pool = TieredMHAKVCache(config, 7, torch.device("cpu"), torch.bfloat16)
            slots = torch.tensor([1, 3, 0, 5, 2, 4])
            try:
                pool.store_kv(k, v, slots, 0)
                actual = tiered_attention(q, slots.tolist(), lambda block: pool.read_tile(0, block), .5, 2)
                full_k = k.float().repeat_interleave(2, dim=1)
                full_v = v.float().repeat_interleave(2, dim=1)
                scores = torch.einsum("qhd,khd->qhk", q.float(), full_k) * .5
                valid = torch.arange(6)[None, :] <= torch.arange(3, 6)[:, None]
                scores.masked_fill_(~valid[:, None, :], -torch.inf)
                expected = torch.einsum("qhk,khd->qhd", scores.softmax(dim=-1), full_v).bfloat16()
                torch.testing.assert_close(actual, expected)
                self.assertEqual(pool.file.seek(0, 2), (7-2)*pool.row_bytes)
                pool.file.truncate(0)
                marker=Path(directory)/"fault"
                marker.write_bytes(b"0")
                with patch.dict("os.environ",{"FARSTACK_KV_FAULT_FILE":str(marker)}):
                    with self.assertRaisesRegex(OSError,"short FarStack KV read"):
                        pool.read_tile(0,[3])
                self.assertEqual(marker.read_bytes(),b"1")
            finally:
                pool.close()
