"""SSD expert source for the pinned FreeToken experimental patch."""

from .ssd_experts import SSDExpertReader, STAGING_LIMIT_BYTES


class SSDExpertSource:
    def __init__(self, reader, staging):
        self.reader = reader
        self.staging = staging
        self.buffer = staging.numpy()
        self.failed = False

    @classmethod
    def open(cls, model_path, model_config, staging_limit_bytes=STAGING_LIMIT_BYTES):
        import torch
        from freetoken.kernel.pinned import alloc_pinned_tensor

        reader = SSDExpertReader(model_path, staging_limit_bytes)
        try:
            if reader.layers != tuple(range(model_config.num_moe_layers)):
                raise ValueError("SSD expert layers do not match the FreeToken model")
            if any(reader.expert_count(layer) != model_config.num_experts for layer in reader.layers):
                raise ValueError("SSD expert count does not match the FreeToken model")
            return cls(reader, alloc_pinned_tensor(reader.required_staging_bytes, dtype=torch.uint8))
        except BaseException:
            reader.close()
            raise

    def close(self):
        self.reader.close()

    def bank_layouts(self):
        import torch
        from freetoken.layers.quantization import QuantKind
        from freetoken.layers.quantization.ggml_types import mmq_tail_bytes, row_bytes, type_name
        from freetoken.moe.expert_banks import ExpertBanks

        sources = {"gate_up": [], "down": []}
        tails = {"gate_up": [], "down": []}
        tags = []
        for layer in self.reader.layers:
            tags.append(("ggml", type_name(self.reader.extent(layer, "gate").ggml_type),
                         type_name(self.reader.extent(layer, "down").ggml_type)))
            for role, file_role, matrices in (("gate_up", "gate", 2), ("down", "down", 1)):
                extent = self.reader.extent(layer, file_role)
                k, rows = extent.matrix_shape
                packed_row = row_bytes(extent.ggml_type, k)
                if rows * packed_row != extent.bytes_per_expert:
                    raise ValueError(f"invalid packed {file_role} rows in SSD expert layer {layer}")
                sources[role].append(
                    torch.empty((extent.experts, matrices * rows, packed_row), dtype=torch.uint8, device="meta")
                )
                tails[role].append(mmq_tail_bytes(extent.ggml_type, k))
        return ExpertBanks("gguf", sources, kind=QuantKind.GGUF, kernel="ggml",
                           layer_tags=tags, row_tail_bytes=tails)

    def copy_missing(self, cache, layer, *, whole_layer):
        if self.failed:
            raise RuntimeError("SSD expert refill previously failed; restart the engine")
        try:
            count = int(cache.num_indices.item())
            if not 0 <= count <= min(cache.src_indices.numel(), cache.evict_slots.numel()):
                raise RuntimeError("invalid SSD expert miss count")
            if count == 0:
                return
            views = cache.stage_views(layer, 0) if whole_layer else cache.pool_bank_views(layer)
            gate_up, down = views
            experts = cache.src_indices[:count].tolist()
            slots = cache.evict_slots[:count].tolist()
            for expert, slot in zip(experts, slots):
                if not 0 <= slot < gate_up.size(0) or not 0 <= slot < down.size(0):
                    raise RuntimeError("SSD expert destination slot out of range")
                parts = self.reader.read_into(layer, expert, self.buffer)
                combined = self.staging[parts["gate"].start:parts["up"].stop]
                gate_up[slot].copy_(combined.view_as(gate_up[slot]), non_blocking=False)
                down[slot].copy_(self.staging[parts["down"]].view_as(down[slot]), non_blocking=False)
        except BaseException:
            # The device planner has already tagged these slots as populated.
            self.failed = True
            self.close()
            raise
