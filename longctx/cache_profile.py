"""Persist approved cache capacity preferences for one engine/model/GPU profile."""
import hashlib
import http.client
import json
import os
import tempfile

from .backend import BackendError
from .cache_control import POOLS, plan, snapshot, uint


def profile_path(backend, config):
    def identity(path):
        info = path.stat()
        return [str(path), info.st_size, info.st_mtime_ns]

    profile = [identity(config.model), identity(config.freetoken_server),
               backend.decision.gpu_uuid, config.context, config.output_reserve, config.ubatch, config.kv_cache_dtype,
               config.freetoken_memory_ratio, config.kv_tokens, config.expert_slots]
    # Auto uses the existing profile key so previously saved capacities carry over.
    if config.moe_strategy != "auto":
        profile.append(config.moe_strategy)
    if config.ssd_experts_enabled:
        profile.append("ssd_expert_offload")
    name = hashlib.sha256(json.dumps(profile).encode()).hexdigest()
    return config.state_dir / ("cache-" + name + ".json")


def save(backend, config, changes):
    path = profile_path(backend, config)
    try:
        previous = load(path)
    except ValueError:
        # An explicitly applied configuration can replace a damaged profile.
        previous = {}
    data = {**previous, **validated(changes)}
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode="w", encoding="utf-8") as fp:
        temporary = fp.name
        try:
            json.dump(data, fp)
            fp.flush()
            os.fsync(fp.fileno())
            fp.close()
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def validated(changes):
    if not isinstance(changes, dict) or set(changes) - set(POOLS):
        raise ValueError("invalid saved cache profile")
    return {name: uint(value) for name, value in changes.items()}


def load(path):
    try:
        return validated(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return {}


def restore(backend, config):
    try:
        changes = load(profile_path(backend, config))
        if not changes:
            return "default"
        g = snapshot(backend, config)
        if g["active_requests"]:
            return "unavailable"
        pending = {name: value for name, value in changes.items()
                   if value != g["pools"][name]["value"]}
        if pending:
            proposed = plan(g, pending)
            response = backend.json("/v1/cache/rebuild",
                                    dict(proposed["arguments"], mode="if_idle", timeout=300),
                                    timeout=310)
            if not isinstance(response, dict) or response.get("status") != "ok":
                return "unavailable"
            g = snapshot(backend, config)
        return ("restored" if all(g["pools"][name]["value"] == value
                                  for name, value in changes.items()) else "unavailable")
    except (OSError, ValueError, KeyError, TypeError, BackendError, http.client.HTTPException):
        return "unavailable"
