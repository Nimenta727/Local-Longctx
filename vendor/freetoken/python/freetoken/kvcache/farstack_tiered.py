"""FarStack experimental BF16 MHA pool with bounded host rows and SSD backing."""
from collections import OrderedDict
from contextlib import contextmanager
from errno import ENOSPC
import os
from pathlib import Path
from shutil import disk_usage
from tempfile import TemporaryFile

import torch

from .mha_pool import MHAKVCache


class TieredMHAKVCache(MHAKVCache):
    tile = 128

    def __init__(self, config, num_pages, device, dtype):
        model = config.model_config
        self.ram_limit = config.farstack_kv_ram_mib * 2**20
        self.resident = min(config.farstack_kv_gpu_tokens, num_pages)
        self.disk_path = Path(config.farstack_kv_dir)
        with self._disk_operation():
            self.disk_path.mkdir(parents=True, exist_ok=True)
            self.file = TemporaryFile(dir=self.disk_path, buffering=0)
        self.rows = OrderedDict()
        try:
            super().__init__(model.num_kv_heads, model.num_layers, model.head_dim,
                             num_pages, 1, dtype, device)
        except BaseException:
            self.file.close()
            raise

    def _alloc(self, layers, pages, page_size, heads):
        self.pages = pages
        self.row_shape = (2, heads, self._head_dim)
        self.row_bytes = 4 * heads * self._head_dim
        self.gpu = torch.empty((layers, self.resident, *self.row_shape),
                               dtype=self.dtype, device=self.device)
        disk_bytes = (pages - self.resident) * layers * self.row_bytes
        with self._disk_operation():
            if disk_bytes > disk_usage(self.disk_path).free:
                raise OSError(ENOSPC, "Active SSD KV backing exceeds currently free disk space")
            self.file.truncate(disk_bytes)

    @staticmethod
    @contextmanager
    def _disk_operation():
        try:
            yield
        except OSError:
            marker = os.environ.get("FARSTACK_KV_FAULT_FILE")
            if marker:
                try:
                    with Path(marker).open("r+b", buffering=0) as signal:
                        signal.write(b"1")
                except OSError:
                    pass
            raise

    def unit_bytes(self):
        return self.row_bytes * self.num_layers, 0

    def close(self):
        self.file.close()

    def _seek(self, layer, slot):
        self.file.seek((layer * (self.pages - self.resident) + slot - self.resident) * self.row_bytes)

    def _remember(self, key, value):
        if self.ram_limit >= self.row_bytes:
            self.rows[key] = value
            self.rows.move_to_end(key)
            if len(self.rows) * self.row_bytes > self.ram_limit:
                self.rows.popitem(last=False)

    def store_kv(self, k, v, out_loc, layer_id):
        slots = out_loc.tolist()
        combined = torch.stack((k.reshape(len(slots), *self.row_shape[1:]),
                                v.reshape(len(slots), *self.row_shape[1:])), dim=1)
        for slot, row in zip(slots, combined):
            if slot < self.resident:
                self.gpu[layer_id, slot].copy_(row)
                continue
            payload = row.cpu().contiguous().view(torch.uint8).numpy().tobytes()
            with self._disk_operation():
                self._seek(layer_id, slot)
                if self.file.write(payload) != self.row_bytes:
                    raise OSError("short FarStack KV write")
            self._remember((layer_id, slot), payload)

    def read_tile(self, layer, slots):
        result = torch.empty((len(slots), *self.row_shape), dtype=self.dtype, device=self.device)
        for offset, slot in enumerate(slots):
            if slot < self.resident:
                result[offset].copy_(self.gpu[layer, slot])
                continue
            key = (layer, slot)
            payload = self.rows.get(key)
            if payload is None:
                with self._disk_operation():
                    self._seek(layer, slot)
                    payload = self.file.read(self.row_bytes)
                    if len(payload) != self.row_bytes:
                        raise OSError("short FarStack KV read")
            self._remember(key, payload)
            row = torch.frombuffer(bytearray(payload), dtype=self.dtype).reshape(self.row_shape)
            result[offset].copy_(row)
        return result[:, 0], result[:, 1]


def tiered_attention(q, slots, read, scale, tile=128):
    """Exact causal GQA reduction across ordered KV tiles with FP32 accumulators."""
    query_count, query_heads, width = q.shape
    positions = torch.arange(len(slots) - query_count, len(slots), device=q.device)
    output = normalizer = maximum = query = None
    for start in range(0, len(slots), tile):
        k, v = read(slots[start:start + tile])
        if query is None:
            kv_heads = k.shape[1]
            query = q.float().reshape(query_count, kv_heads, query_heads // kv_heads, width)
            output = torch.zeros_like(query)
            stat_shape = query.shape[:-1]
            normalizer = torch.zeros(stat_shape, device=q.device)
            maximum = torch.full(stat_shape, -torch.inf, device=q.device)

        key_positions = torch.arange(start, start + len(k), device=q.device)
        scores = torch.einsum("qhgd,khd->qhgk", query, k.float()) * scale
        allowed = key_positions[None, :] <= positions[:, None]
        scores.masked_fill_(~allowed[:, None, None, :], -torch.inf)
        next_max = torch.maximum(maximum, scores.amax(dim=-1))
        safe_max = torch.where(torch.isfinite(next_max), next_max, 0.)
        carry = torch.exp(maximum - safe_max)
        weights = torch.exp(scores - safe_max[..., None])
        output = output * carry[..., None] + torch.einsum("qhgk,khd->qhgd", weights, v.float())
        normalizer = normalizer * carry + weights.sum(dim=-1)
        maximum = next_max
    return (output / normalizer[..., None]).reshape_as(q).to(q.dtype)
