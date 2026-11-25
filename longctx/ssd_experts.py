"""Experimental bounded Qwen3-MoE GGUF expert reads."""
from dataclasses import dataclass
from pathlib import Path
import os
import re
from threading import Lock

EXPERT_WEIGHT = re.compile(r"blk\.(\d+)\.ffn_(gate|up|down)_exps\.weight")
ROLES = ("gate", "up", "down")
SUPPORTED_QUANTS = frozenset(("Q4_K", "Q6_K"))
STAGING_LIMIT_BYTES = 4 * 2**20


@dataclass(frozen=True)
class ExpertExtent:
    offset: int
    bytes_per_expert: int
    experts: int
    matrix_shape: tuple[int, ...]
    ggml_type: int


def index_qwen3(path, file_size):
    """Keep only offsets and sizes after reading metadata with upstream gguf."""
    try:
        from gguf import GGUFEndian, GGUFReader
    except ImportError as exc:
        raise ValueError("install the optional gguf reader (gguf>=0.19,<0.20)") from exc

    reader = GGUFReader(path, mode="r")
    architecture = reader.get_field("general.architecture")
    splits = reader.get_field("split.count")
    count = reader.get_field("qwen3moe.expert_count")
    if architecture is None or architecture.contents() != "qwen3moe":
        raise ValueError("expected a qwen3moe GGUF")
    if reader.endianess != GGUFEndian.LITTLE or (splits is not None and splits.contents() != 1):
        raise ValueError("expected a single-file little-endian GGUF")
    if count is None or type(count.contents()) is not int or count.contents() <= 0:
        raise ValueError("missing Qwen3-MoE expert count")
    experts = count.contents()
    banks = {}
    ranges = []
    for tensor in reader.tensors:
        match = EXPERT_WEIGHT.fullmatch(tensor.name)
        if not match:
            if re.fullmatch(r"blk\.\d+\.ffn_.*_exps\.(weight|bias)", tensor.name):
                raise ValueError(f"unsupported expert tensor: {tensor.name}")
            continue
        layer, role = int(match[1]), match[2]
        dims = tuple(int(n) for n in tensor.shape)
        size, offset = int(tensor.n_bytes), int(tensor.data_offset)
        if (tensor.tensor_type.name not in SUPPORTED_QUANTS or len(dims) != 3
                or dims[-1] != experts or any(n < 1 for n in dims)
                or size <= 0 or size % experts):
            raise ValueError(f"unsupported expert layout: {tensor.name}")
        if offset < reader.data_offset or offset + size > file_size:
            raise ValueError(f"expert extent exceeds GGUF: {tensor.name}")
        parts = banks.setdefault(layer, {})
        if role in parts:
            raise ValueError("duplicate expert bank")
        parts[role] = ExpertExtent(offset, size // experts, experts, dims[:2], int(tensor.tensor_type))
        ranges.append((offset, offset + size))
    if not banks or any(set(parts) != set(ROLES) for parts in banks.values()):
        raise ValueError("missing gate, up or down expert bank")
    for layer, parts in banks.items():
        gate, up, down = (parts[role] for role in ROLES)
        if (gate.matrix_shape != up.matrix_shape or gate.matrix_shape != down.matrix_shape[::-1]
                or gate.ggml_type != up.ggml_type):
            raise ValueError(f"incompatible expert matrix shapes in layer {layer}")
    ranges.sort()
    if any(end > start for (_, end), (start, _) in zip(ranges, ranges[1:])):
        raise ValueError("overlapping expert extents")
    return banks


def _file_identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


class SSDExpertReader:
    """Read into caller-owned contiguous memory, with no application weight cache."""

    def __init__(self, path, staging_limit_bytes):
        if type(staging_limit_bytes) is not int or staging_limit_bytes < 1:
            raise ValueError("staging limit must be a positive byte count")
        path = Path(path)
        self._file = path.open("rb", buffering=0)
        self._lock = Lock()
        try:
            info = os.fstat(self._file.fileno())
            self._banks = index_qwen3(path, info.st_size)
            if _file_identity(path.stat()) != _file_identity(info):
                raise ValueError("GGUF changed while building the expert index")
            self.required_staging_bytes = max(
                sum(extent.bytes_per_expert for extent in parts.values())
                for parts in self._banks.values()
            )
            if self.required_staging_bytes > staging_limit_bytes:
                raise ValueError(f"one expert requires {self.required_staging_bytes} staging bytes")
            self.host_weight_estimate_bytes = info.st_size - sum(
                part.bytes_per_expert * part.experts
                for parts in self._banks.values() for part in parts.values()
            ) + self.required_staging_bytes
        except BaseException:
            self._file.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        with self._lock:
            self._file.close()

    @property
    def layers(self):
        return tuple(sorted(self._banks))

    def expert_count(self, layer):
        return self._banks[layer]["gate"].experts

    def extent(self, layer, role):
        return self._banks[layer][role]

    def read_into(self, layer, expert, destination):
        """Fill gate/up/down bytes in order and return their slices."""
        parts = self._banks[layer]
        if type(expert) is not int or not 0 <= expert < parts["gate"].experts:
            raise ValueError("expert ID is out of range")
        with memoryview(destination).cast("B") as buffer:
            size = sum(part.bytes_per_expert for part in parts.values())
            if buffer.readonly or len(buffer) < size:
                raise ValueError(f"destination must have at least {size} writable contiguous bytes")
            cursor, slices = 0, {}
            with self._lock:
                for role in ROLES:
                    part = parts[role]
                    end = cursor + part.bytes_per_expert
                    self._file.seek(part.offset + expert * part.bytes_per_expert)
                    position = cursor
                    while position < end:
                        with buffer[position:end] as remaining:
                            read = self._file.readinto(remaining)
                        if not read:
                            raise EOFError("short GGUF expert read")
                        position += read
                    slices[role] = slice(cursor, end)
                    cursor = end
            return slices
