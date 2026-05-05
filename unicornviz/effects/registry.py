"""
Effect auto-discovery registry.

``get_effects()`` imports every ``*.py`` module in the ``effects/`` package
(except ``base.py`` and ``registry.py`` themselves), collects all concrete
subclasses of ``BaseEffect``, and returns them sorted by ``NAME``.

Adding a new effect
-------------------
Simply create a new file in ``unicornviz/effects/`` that subclasses
``BaseEffect``.  It will be discovered automatically on the next run.

Caching
-------
Results are cached after the first call so repeated calls (e.g., from tests)
do not re-import modules.
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Type

from unicornviz.effects.base import BaseEffect

log = logging.getLogger(__name__)

# Ordered list of effect classes (loaded at import time)
_registry: list[Type[BaseEffect]] = []


def _discover() -> None:
    pkg_dir = Path(__file__).parent
    for path in sorted(pkg_dir.glob("*.py")):
        if path.stem in ("__init__", "base", "registry"):
            continue
        module_name = f"unicornviz.effects.{path.stem}"
        try:
            mod = importlib.import_module(module_name)
        except Exception as exc:
            log.warning("Skipping effect module %s: %s", path.name, exc)
            continue
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if (
                issubclass(obj, BaseEffect)
                and obj is not BaseEffect
                and obj not in _registry
            ):
                _registry.append(obj)
                log.debug("Registered effect: %s", obj.NAME)


def get_effects() -> list[Type[BaseEffect]]:
    if not _registry:
        _discover()
    return list(_registry)
