"""TOML config loader with sane defaults."""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


_DEFAULTS: dict[str, Any] = {
    "window": {
        "width": 1920,
        "height": 1080,
        "fullscreen": False,
        "title": "Unicorn Viz",
    },
    "demo": {
        "mode": "sequential",
        "effect_duration": 20,
        "transition": "crossfade",
        "transition_duration": 1.0,
    },
    "audio": {
        "device": "",
        "fft_bands": 512,
        "buffer_seconds": 2.0,
    },
    "midi": {
        "device": "",
    },
    "ansi": {
        "ansi_dir": "assets/ansi",
    },
    "effects": {},
    "playlist": {
        "sequence": [],
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


class Config:
    def __init__(self, path: str | Path = "config.toml") -> None:
        self._data = dict(_DEFAULTS)
        p = Path(path)
        if p.exists():
            with p.open("rb") as f:
                user = tomllib.load(f)
            self._data = _deep_merge(self._data, user)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, *keys: str, default: Any = None) -> Any:
        node = self._data
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node
