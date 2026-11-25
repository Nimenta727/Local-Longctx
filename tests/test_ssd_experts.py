from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import replace
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from longctx.freetoken_ssd import SSDExpertSource
from longctx.ssd_experts import ExpertExtent, SSDExpertReader
from longctx.config import Config, GIB, memory_plan
from longctx.freetoken import command
from longctx.hardware import GPU, Hardware
from longctx.scheduler import choose


class SSDExpertTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "experts.gguf"
        self.path.write_bytes(b"abcdABCD012345")
        mock = patch("longctx.ssd_experts.index_qwen3", return_value={
            0: {"gate": ExpertExtent(0, 2, 2, (1, 2), 12),
                "up": ExpertExtent(4, 2, 2, (1, 2), 12),
                "down": ExpertExtent(8, 3, 2, (2, 1), 14)},
        })
        mock.start()
        self.addCleanup(mock.stop)

    def test_reads_each_expert_into_the_same_bounded_buffer(self):
        complete_banks = self.path.read_bytes()
        buffer = bytearray(7)
        with SSDExpertReader(self.path, len(buffer)) as reader:
            warm = reader.read_into(0, 1, buffer)
            self.assertEqual(bytes(buffer), complete_banks[2:4] + complete_banks[6:8] + complete_banks[11:14])
            cold = reader.read_into(0, 0, buffer)
            self.assertEqual(bytes(buffer), complete_banks[0:2] + complete_banks[4:6] + complete_banks[8:11])
            self.assertEqual(warm, cold)
            self.assertEqual(bytes(buffer[cold["up"]]), b"AB")

    def test_rejects_invalid_requests_and_partial_weight_files(self):
        with self.assertRaisesRegex(ValueError, "one expert requires 7 staging bytes"):
            SSDExpertReader(self.path, 6)
        with SSDExpertReader(self.path, 7) as reader:
            with self.assertRaisesRegex(ValueError, "out of range"):
                reader.read_into(0, 2, bytearray(7))
            with self.assertRaisesRegex(ValueError, "writable"):
                reader.read_into(0, 0, bytes(7))
            with self.path.open("r+b") as output:
                output.truncate(13)
            with self.assertRaisesRegex(EOFError, "short GGUF expert read"):
                reader.read_into(0, 1, bytearray(7))

    def test_refill_obeys_slot_map_and_rejects_hits_after_failed_read(self):
        try:
            import torch
        except ImportError:
            self.skipTest("PyTorch is needed to exercise the FreeToken refill adapter")

        def banks():
            return torch.zeros((2, 2, 2), dtype=torch.uint8), torch.zeros((2, 1, 3), dtype=torch.uint8)

        pool, stage = banks(), banks()
        cache = SimpleNamespace(
            num_indices=torch.tensor(1),
            src_indices=torch.tensor([1, 999]),
            evict_slots=torch.tensor([0, 999]),
            pool_bank_views=lambda layer: pool,
            stage_views=lambda layer, buffer_id: stage,
        )
        with SSDExpertReader(self.path, 7) as reader:
            source = SSDExpertSource(reader, torch.empty(7, dtype=torch.uint8))
            source.copy_missing(cache, 0, whole_layer=False)
            self.assertEqual(bytes(pool[0][0].flatten().tolist()), b"cdCD")
            self.assertEqual(bytes(pool[1][0].flatten().tolist()), b"345")
            self.assertEqual(int(pool[0][1].sum()), 0)
            self.assertEqual(int(stage[0].sum()), 0)

            cache.src_indices[:] = torch.tensor([0, 1])
            cache.evict_slots[:] = torch.tensor([1, 0])
            cache.num_indices.fill_(2)
            source.copy_missing(cache, 0, whole_layer=True)
            self.assertEqual(bytes(stage[0][1].flatten().tolist()), b"abAB")
            self.assertEqual(bytes(stage[1][1].flatten().tolist()), b"012")
            self.assertEqual(bytes(stage[0][0].flatten().tolist()), b"cdCD")
            cache.num_indices.zero_()
            source.copy_missing(cache, 0, whole_layer=False)

            with self.path.open("r+b") as output:
                output.truncate(13)
            cache.num_indices.fill_(2)
            with self.assertRaises(EOFError):
                source.copy_missing(cache, 0, whole_layer=False)
            cache.num_indices.zero_()
            with self.assertRaisesRegex(RuntimeError, "restart the engine"):
                source.copy_missing(cache, 0, whole_layer=False)

    def test_startup_budget_only_discounts_expert_weights_when_enabled(self):
        engine = self.path.with_name("ft")
        engine.touch()
        with self.path.open("r+b") as file:
            file.write(b"GGUF")
            file.truncate(8 * GIB)
        mib = 2**20
        with patch("longctx.ssd_experts.index_qwen3", return_value={
            0: {"gate": ExpertExtent(0, mib, 2048, (1, 2), 12),
                "up": ExpertExtent(2 * GIB, mib, 2048, (1, 2), 12),
                "down": ExpertExtent(4 * GIB, mib, 2048, (2, 1), 14)},
        }):
            config = Config(engine, self.path, model_is_moe=True, freetoken_model_verified=True,
                            moe_strategy="offload").validate()
            hw = Hardware("Linux", 8, 16, 5, 300, (GPU("GPU-test", "NVIDIA", 7, 8, "driver"),))
            with self.assertRaisesRegex(ValueError, "available RAM"):
                choose(config, hw)
            gated_off = replace(config, ssd_expert_offload=True).validate()
            self.assertEqual(command(gated_off, choose(config, replace(hw, ram_available_gib=12))),
                             command(config, choose(config, replace(hw, ram_available_gib=12))))
            self.assertEqual(memory_plan(gated_off)["host_weight_estimate_gib"], 8)
            selected = replace(gated_off, experimental_ssd=True, ssd_expert_staging_mib=8).validate()
            self.assertEqual(memory_plan(selected)["host_weight_estimate_gib"], 2 + 3 / 1024)
            decision = choose(selected, hw)
            self.assertEqual(command(selected, decision)[-6:],
                             ["--experimental-ssd-experts", "--experimental-ssd-expert-staging-mib", "8",
                              "--cuda-graph-max-bs", "0", "--disable-moe-prefill-overlap"])
            self.assertNotIn("--experimental-ssd-experts", command(config, decision))
            with self.assertRaisesRegex(ValueError, "available RAM"):
                choose(replace(selected, host_weights_gib=4), hw)
