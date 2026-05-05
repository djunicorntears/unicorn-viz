"""Demo playlist — tracks current effect index and handles advance logic."""
from __future__ import annotations

import random
from typing import Type

from unicornviz.effects.base import BaseEffect
from unicornviz.config import Config


class Playlist:
    def __init__(
        self,
        effect_classes: list[Type[BaseEffect]],
        cfg: Config,
    ) -> None:
        sequence: list[str] = cfg.get("playlist", "sequence", default=[])
        mode: str = cfg.get("demo", "mode", default="sequential")

        if sequence:
            name_map = {cls.__name__: cls for cls in effect_classes}
            filtered = [name_map[n] for n in sequence if n in name_map]
            self._effects = filtered if filtered else effect_classes
        else:
            self._effects = list(effect_classes)

        self._mode = mode
        self._index = 0

    def current(self) -> Type[BaseEffect]:
        return self._effects[self._index]

    def advance(self) -> Type[BaseEffect]:
        if self._mode == "random":
            self._index = random.randrange(len(self._effects))
        else:
            self._index = (self._index + 1) % len(self._effects)
        return self._effects[self._index]

    def go_prev(self) -> Type[BaseEffect]:
        self._index = (self._index - 1) % len(self._effects)
        return self._effects[self._index]

    def go_index(self, i: int) -> Type[BaseEffect]:
        self._index = i % len(self._effects)
        return self._effects[self._index]

    def toggle_random(self) -> None:
        self._mode = "random" if self._mode != "random" else "sequential"

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def index(self) -> int:
        return self._index

    @property
    def effects(self) -> list[Type[BaseEffect]]:
        return self._effects
