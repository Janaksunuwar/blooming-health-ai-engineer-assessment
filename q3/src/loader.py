"""Input loading and schema validation for the Q3 evaluator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_dataset(path: Path) -> dict[str, Any]:
    data = _load_json(path)
    required = {"agent_config", "threads"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"Dataset is missing required keys: {sorted(missing)}")
    if not isinstance(data["threads"], list):
        raise ValueError("Dataset key 'threads' must be a list")
    for thread in data["threads"]:
        for key in ("thread_id", "messages"):
            if key not in thread:
                raise ValueError(f"Thread is missing required key: {key}")
        if not isinstance(thread["messages"], list):
            raise ValueError(f"Thread {thread['thread_id']} messages must be a list")
    return data


def load_captured_fields(path: Path) -> dict[str, Any]:
    data = _load_json(path)
    if data == {}:
        return {"threads": {}}
    if "threads" not in data or not isinstance(data["threads"], dict):
        raise ValueError("Captured-fields JSON must contain an object key 'threads'")
    return data


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data
