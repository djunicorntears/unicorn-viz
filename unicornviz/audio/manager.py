"""
AudioManager — owns AudioCapture + Analyzer, exposes get_audio_data().
Also manages MIDI (stub for now, full impl in Phase 6).
"""
from __future__ import annotations

import logging

from unicornviz.effects.base import AudioData
from unicornviz.audio.capture import AudioCapture
from unicornviz.audio.analyzer import Analyzer
from unicornviz.config import Config

log = logging.getLogger(__name__)


class AudioManager:
    def __init__(self, cfg: Config) -> None:
        device_hint = cfg.get("audio", "device", default="")
        fft_bands = cfg.get("audio", "fft_bands", default=512)
        buffer_seconds = cfg.get("audio", "buffer_seconds", default=2.0)
        latency = cfg.get("audio", "latency", default="high")
        try_alsa_loopback = cfg.get("audio", "try_alsa_loopback", default=True)
        # "reactivity" controls how strongly visuals respond to audio features.
        # Keep legacy "gain" as fallback for backward compatibility.
        self._reactivity = float(
            cfg.get("audio", "reactivity", default=cfg.get("audio", "gain", default=1.0))
        )
        self._capture = AudioCapture(
            device_hint=device_hint,
            buffer_seconds=buffer_seconds,
            latency=latency,
            try_alsa_loopback=try_alsa_loopback,
        )
        self._analyzer = Analyzer(fft_bands=fft_bands)
        self._last_data = AudioData()

    def start(self) -> None:
        self._capture.start()

    def stop(self) -> None:
        self._capture.stop()

    def get_audio_data(self) -> AudioData:
        """Called every frame from the main loop."""
        self._capture.maybe_fallback()
        block = self._capture.get_block()
        data = self._analyzer.process(block)
        if self._reactivity != 1.0:
            data.bass   = min(1.0, data.bass   * self._reactivity)
            data.mid    = min(1.0, data.mid    * self._reactivity)
            data.treble = min(1.0, data.treble * self._reactivity)
            if data.fft is not None:
                import numpy as _np
                data.fft = _np.clip(data.fft * self._reactivity, 0.0, 1.0)
        self._last_data = data
        return self._last_data
