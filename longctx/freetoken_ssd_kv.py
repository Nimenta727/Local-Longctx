"""A bounded, opt-in checkpoint for FreeToken's plain BF16 MHA prefix cache."""

import hashlib
import json
import logging
import os
from pathlib import Path
import struct
import tempfile

MAX_CHECKPOINT_BYTES = 256 * 2**20
HEADER = struct.Struct("<8s32s32sI")
MAGIC = b"LCKV0001"
DIGEST_BYTES = 32
logger = logging.getLogger(__name__)


def prefix_digest(ids):
    return hashlib.sha256(ids.cpu().contiguous().numpy().astype("<i4", copy=False)).digest()


class SSDPrefixCheckpoint:
    def __init__(self, path, pool, identity, max_bytes=MAX_CHECKPOINT_BYTES):
        import torch

        buffer = pool._kv_buffer
        if buffer.dtype != torch.bfloat16 or pool._scale_buffer is not None or buffer.shape[3] != 1:
            raise ValueError("SSD KV requires an unquantized BF16 MHA pool with page size 1")
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.pool = pool
        layout = (tuple(buffer.shape[:2]), tuple(buffer.shape[3:]), str(buffer.dtype))
        self.identity = hashlib.sha256(json.dumps((identity, layout), sort_keys=True).encode()).digest()
        self.bytes_per_token = pool.unit_bytes()[0]
        self.max_tokens = (max_bytes - HEADER.size - DIGEST_BYTES) // self.bytes_per_token
        self._last_written = None

    @classmethod
    def from_engine(cls, config, pool):
        model = Path(config.model_path).resolve()
        checkpoint = Path(config.experimental_ssd_kv)
        if checkpoint.resolve() == model or (checkpoint.exists() and checkpoint.samefile(model)):
            raise ValueError("SSD KV checkpoint path must be different from the model file")
        info = model.stat()
        identity = (str(model), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                    info.st_ctime_ns, config.attention_backend, config.moe_strategy,
                    config.quant_backend, config.experimental_ssd_experts,
                    config.hf_overrides, str(config.model_config.rotary_config))
        return cls(checkpoint, pool, identity, config.experimental_ssd_kv_limit_mib*2**20)

    def _layers(self):
        # Rebuild replaces the buffer in place on the same pool object.
        for kind in self.pool._kv_buffer:
            for layer in kind:
                yield layer.flatten(0, 1)

    def clear(self):
        self.path.unlink(missing_ok=True)
        self._last_written = None

    def save(self, ids, indices):
        import torch

        count = min(len(ids), self.max_tokens)
        if count <= 0:
            return
        prefix = prefix_digest(ids[:count])
        if self._last_written == (count, prefix):
            return
        header = HEADER.pack(MAGIC, self.identity, prefix, count)
        digest = hashlib.sha256(header)
        indices = indices[:count].long()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as output:
                temporary = output.name
                output.write(header)
                for layer in self._layers():
                    rows = layer.index_select(0, indices).cpu().view(torch.uint8).numpy()
                    digest.update(rows)
                    output.write(rows)
                output.write(digest.digest())
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
            self._last_written = count, prefix
        except OSError as exc:
            logger.warning("SSD KV checkpoint write failed: %s", exc)
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    logger.warning("SSD KV temporary file cleanup failed: %s", exc)

    def restore(self, ids, manager, cached_len):
        """Populate unused slots. Publish them to radix only after checking the digest."""
        import torch

        try:
            source = self.path.open("rb")
        except FileNotFoundError:
            return False
        except OSError as exc:
            logger.warning("SSD KV checkpoint open failed: %s", exc)
            return False
        indices = None
        try:
            with source:
                header = source.read(HEADER.size)
                if len(header) != HEADER.size:
                    raise ValueError("truncated header")
                magic, identity, prefix, count = HEADER.unpack(header)
                if magic != MAGIC or identity != self.identity:
                    return False
                if (not 0 < count <= self.max_tokens
                        or os.fstat(source.fileno()).st_size != HEADER.size + count * self.bytes_per_token + DIGEST_BYTES):
                    raise ValueError("invalid payload size")
                if count <= cached_len or count > min(len(ids), len(manager.free_slots)):
                    return False
                if prefix_digest(ids[:count]) != prefix:
                    return False

                indices = manager._allocate(count)
                destinations = indices.long()
                digest = hashlib.sha256(header)
                for layer in self._layers():
                    row_shape = (count, *layer.shape[1:])
                    payload = bytearray(count * layer[0].numel() * layer.element_size())
                    if source.readinto(payload) != len(payload):
                        raise ValueError("truncated payload")
                    digest.update(payload)
                    rows = torch.frombuffer(payload, dtype=layer.dtype).view(row_shape)
                    layer.index_copy_(0, destinations, rows.to(layer.device))
                if source.read(DIGEST_BYTES) != digest.digest() or source.read(1):
                    raise ValueError("checksum mismatch")
            already_cached, _ = manager.prefix_cache.insert_prefix(ids[:count], indices)
            manager._free(indices[:already_cached])
            indices = None
            self._last_written = count, prefix
            return True
        except (OSError, ValueError) as exc:
            self._last_written = None
            logger.warning("SSD KV checkpoint ignored: %s", exc)
            return False
        finally:
            if indices is not None:
                manager._free(indices)
