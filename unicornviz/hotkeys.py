"""Hotkey handler — maps SDL keysyms to app/playlist/overlay actions."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import sdl2

if TYPE_CHECKING:
    from unicornviz.app import App
    from unicornviz.playlist import Playlist
    from unicornviz.overlays import Overlays
    from unicornviz.audio.manager import AudioManager

log = logging.getLogger(__name__)


class HotkeyHandler:
    def __init__(
        self,
        app: "App",
        playlist: "Playlist",
        overlays: "Overlays",
        audio_manager: "AudioManager",
    ) -> None:
        self._app = app
        self._playlist = playlist
        self._overlays = overlays
        self._audio = audio_manager

    def handle(self, sym: int, mod: int) -> None:
        a = self._app
        p = self._playlist
        o = self._overlays

        if sym == sdl2.SDLK_ESCAPE:
            a._running = False  # noqa: SLF001

        elif sym in (sdl2.SDLK_n, sdl2.SDLK_RIGHT):
            cls = p.advance()
            a.goto_effect(cls)
            o.flash_name(cls.NAME)

        elif sym in (sdl2.SDLK_p, sdl2.SDLK_LEFT):
            cls = p.go_prev()
            a.goto_effect(cls)
            o.flash_name(cls.NAME)

        elif sym == sdl2.SDLK_f:
            a.toggle_fullscreen()

        elif sym == sdl2.SDLK_SPACE:
            a.toggle_pause()
            o.flash_message("PAUSED" if a.paused else "RESUMED", 1.5)

        elif sym == sdl2.SDLK_TAB:
            o.toggle_name_overlay()

        elif sym == sdl2.SDLK_h:
            o.toggle_help()

        elif sym == sdl2.SDLK_a:
            o.toggle_audio_selector()

        elif sym == sdl2.SDLK_m:
            o.toggle_midi_selector()

        elif sym == sdl2.SDLK_r:
            p.toggle_random()
            mode = p.mode.upper()
            o.flash_message(f"Playlist: {mode}", 1.5)

        elif sym == sdl2.SDLK_PLUS or sym == sdl2.SDLK_EQUALS:
            effect = a._current_effect  # noqa: SLF001
            if effect and "speed" in effect.parameters:
                effect.parameters["speed"] = min(
                    effect.parameters["speed"] * 1.25, 10.0
                )

        elif sym == sdl2.SDLK_MINUS:
            effect = a._current_effect  # noqa: SLF001
            if effect and "speed" in effect.parameters:
                effect.parameters["speed"] = max(
                    effect.parameters["speed"] * 0.8, 0.05
                )

        elif sdl2.SDLK_1 <= sym <= sdl2.SDLK_9:
            idx = sym - sdl2.SDLK_1
            cls = p.go_index(idx)
            a.goto_effect(cls)
            o.flash_name(cls.NAME)

        elif sym == sdl2.SDLK_s:
            self._screenshot()

    def _screenshot(self) -> None:
        import datetime
        import numpy as np
        from PIL import Image

        ctx = self._app._ctx  # noqa: SLF001
        if ctx is None:
            return
        w, h = self._app._width, self._app._height  # noqa: SLF001
        data = ctx.screen.read(components=3)
        img = Image.frombytes("RGB", (w, h), data)
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"unicornviz_{ts}.png"
        img.save(path)
        self._overlays.flash_message(f"Screenshot: {path}", 3.0)
        log.info("Screenshot saved: %s", path)
