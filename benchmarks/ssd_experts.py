"""Probe raw SSD expert reads for a single-file Qwen3-MoE GGUF."""
import argparse
import hashlib
import json
from pathlib import Path
import random
from statistics import median
from time import perf_counter

from longctx.ssd_experts import ROLES, SSDExpertReader


def expert_pair(value):
    try:
        layer, expert = (int(part) for part in value.split(":"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected LAYER:EXPERT") from exc
    if layer < 0 or expert < 0:
        raise argparse.ArgumentTypeError("layer and expert must be nonnegative")
    return layer, expert


def replay(path, reader, pairs, verify):
    reference = None
    if verify:
        from gguf import GGUFReader
        reference = {tensor.name: tensor for tensor in GGUFReader(path).tensors}

    staging = bytearray(reader.required_staging_bytes)
    samples = []
    with memoryview(staging) as raw:
        for layer, expert in pairs:
            start = perf_counter()
            fields = reader.read_into(layer, expert, raw)
            elapsed = perf_counter() - start
            hashes = {}
            for role, span in fields.items():
                with raw[span] as part:
                    if reference is not None:
                        name = f"blk.{layer}.ffn_{role}_exps.weight"
                        with memoryview(reference[name].data[expert]).cast("B") as expected:
                            if part != expected:
                                raise ValueError(f"GGUF expert bytes differ at {layer}:{expert}:{role}")
                    hashes[role] = hashlib.sha256(part).hexdigest()
            samples.append({"layer": layer, "expert": expert, "bytes": fields[ROLES[-1]].stop,
                            "read_ms": elapsed * 1000, "sha256": hashes})
    return {
        "model_bytes": path.stat().st_size,
        "indexed_layers": len(reader.layers),
        "staging_bytes": len(staging),
        "reference_verified": verify,
        "median_read_ms": median(sample["read_ms"] for sample in samples),
        "samples": samples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--staging-mib", type=int, default=4)
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--expert", type=expert_pair, action="append", help="repeatable LAYER:EXPERT selection")
    parser.add_argument("--verify", action="store_true", help="compare with gguf's mapped expert slices")
    args = parser.parse_args()
    if args.samples < 1 or args.staging_mib < 1:
        parser.error("samples and staging capacity must be positive")
    rng = random.Random(0)
    try:
        with SSDExpertReader(args.model, args.staging_mib * (1 << 20)) as reader:
            pairs = args.expert or [
                (layer, rng.randrange(reader.expert_count(layer)))
                for layer in (rng.choice(reader.layers) for _ in range(args.samples))
            ]
            report = replay(args.model, reader, pairs, args.verify)
    except (OSError, ValueError, EOFError, KeyError) as exc:
        parser.exit(1, f"SSD expert probe: {exc}\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
