"""Atomic, run-scoped checkpoints for interrupted optimization jobs."""

import hashlib
import json
import os
import pickle
from pathlib import Path

_TRANSIENT_CONFIG_KEYS = {
    "checkpoint_dir",
    "checkpoint_enabled",
    "checkpoint_keep_completed",
    "checkpoint_resume",
    "checkpoint_save_every",
    "concurrent_runs",
    "keep_workspaces",
    "log_dir",
    "workspace_dir",
    "workspace_root",
}


def _json_compatible(value):
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def build_fingerprint(config, algorithm, parameters):
    stable_config = {
        key: value for key, value in config.items() if key not in _TRANSIENT_CONFIG_KEYS
    }
    payload = {
        "algorithm": algorithm,
        "config": _json_compatible(stable_config),
        "parameters": _json_compatible(parameters),
        "schema": 1,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class CheckpointManager:
    """Save and restore one optimization run at generation boundaries."""

    def __init__(self, config, algorithm, parameters):
        self.enabled = bool(config.get("checkpoint_enabled", False))
        self.resume = bool(config.get("checkpoint_resume", True))
        self.save_every = int(config.get("checkpoint_save_every", 1))
        self.keep_completed = bool(config.get("checkpoint_keep_completed", False))
        if self.save_every < 1:
            raise ValueError("Checkpoint SaveEvery must be at least 1.")

        checkpoint_dir = Path(config.get("checkpoint_dir", "checkpoints"))
        site_name = str(config.get("site_name", "Unknown"))
        opt_mode = int(config.get("opt_mode", 0))
        safe_site = "".join(character if character.isalnum() else "_" for character in site_name)
        self.path = checkpoint_dir / f"{safe_site}_mode{opt_mode}_{algorithm}.pkl"
        self.fingerprint = build_fingerprint(config, algorithm, parameters)

    def load(self):
        if not self.enabled or not self.resume or not self.path.is_file():
            return None
        with self.path.open("rb") as checkpoint_file:
            checkpoint = pickle.load(checkpoint_file)
        if checkpoint.get("fingerprint") != self.fingerprint:
            raise ValueError(
                f"Checkpoint settings do not match the current optimization: {self.path}"
            )
        if checkpoint.get("completed"):
            return None
        return checkpoint["state"]

    def save(self, generation, state, *, force=False):
        if not self.enabled or (generation % self.save_every != 0 and not force):
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        checkpoint = {
            "completed": False,
            "fingerprint": self.fingerprint,
            "generation": generation,
            "state": state,
            "version": 1,
        }
        with temporary_path.open("wb") as checkpoint_file:
            pickle.dump(checkpoint, checkpoint_file, protocol=pickle.HIGHEST_PROTOCOL)
            checkpoint_file.flush()
            os.fsync(checkpoint_file.fileno())
        os.replace(temporary_path, self.path)

    def complete(self):
        if not self.enabled or not self.path.exists():
            return
        if not self.keep_completed:
            self.path.unlink()
            return
        with self.path.open("rb") as checkpoint_file:
            checkpoint = pickle.load(checkpoint_file)
        checkpoint["completed"] = True
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary_path.open("wb") as checkpoint_file:
            pickle.dump(checkpoint, checkpoint_file, protocol=pickle.HIGHEST_PROTOCOL)
            checkpoint_file.flush()
            os.fsync(checkpoint_file.fileno())
        os.replace(temporary_path, self.path)
