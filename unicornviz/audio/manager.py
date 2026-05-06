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
        self._gain = float(cfg.get("audio", "gain", default=1.0))
        self._capture = AudioCapture(
            device_hint=device_hint,
            buffer_seconds=buffer_seconds,
        )
        self._analyzer = Analyzer(fft_bands=fft_bands)
        self._last_data = AudioData()

    def start(self) -> None:
        self._capture.start()

    def stop(self) -> None:
        self._capture.stop()

    def get_audio_data(self) -> AudioData:
        """Called every frame from the main loop."""
        block = self._capture.get_block()
        data = self._analyzer.process(block)
        if self._gain != 1.0:
            data.bass   = min(1.0, data.bass   * self._gain)
            data.mid    = min(1.0, data.mid    * self._gain)
            data.treble = min(1.0, data.treble * self._gain)
            if data.fft is not None:
                import numpy as _np
                data.fft = _np.clip(data.fft * self._gain, 0.0, 1.0)
        self._last_data = data
        return self._last_data
