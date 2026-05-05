"""
FFT analyzer + beat detector.
Consumes PCM blocks from AudioCapture and produces AudioData snapshots.
"""
from __future__ import annotations

import numpy as np

from unicornviz.effects.base import AudioData

_FFT_BANDS = 512
_SMOOTHING = 0.75       # exponential smoothing coefficient
_ONSET_WINDOW = 43      # ~1 s of history at 60 fps for spectral flux
_BEAT_THRESHOLD = 1.4   # standard deviations above mean


class Analyzer:
    """
    Call `process(pcm)` each frame (pcm = float32 mono array).
    Returns an AudioData snapshot.
    """

    def __init__(self, fft_bands: int = _FFT_BANDS) -> None:
        self._bands = fft_bands
        self._smoothed = np.zeros(fft_bands, dtype=np.float32)
        # Spectral flux history for beat detection
        self._flux_history: list[float] = [0.0] * _ONSET_WINDOW
        self._prev_spectrum = np.zeros(fft_bands, dtype=np.float32)
        self._beat_cooldown = 0.0   # frames remaining before next beat

    def process(self, pcm: np.ndarray | None) -> AudioData:
        data = AudioData()

        if pcm is None or len(pcm) == 0:
            return data

        # Window + FFT
        n = len(pcm)
        window = np.hanning(n).astype(np.float32)
        windowed = pcm[:n] * window
        spectrum = np.abs(np.fft.rfft(windowed, n=self._bands * 2))
        spectrum = spectrum[: self._bands].astype(np.float32)

        # Normalise
        max_val = spectrum.max()
        if max_val > 1e-6:
            spectrum /= max_val

        # Smoothed FFT
        self._smoothed = (
            self._smoothed * _SMOOTHING + spectrum * (1.0 - _SMOOTHING)
        )
        data.fft = self._smoothed.copy()

        # Waveform (last 512 samples normalised)
        wlen = min(512, len(pcm))
        wform = pcm[-wlen:]
        peak = np.abs(wform).max()
        data.waveform = (wform / peak if peak > 1e-6 else wform).astype(np.float32)

        # Band energy
        lo = max(1, self._bands // 32)   # bass: ~0–1 kHz
        mid_lo = self._bands // 8
        mid_hi = self._bands // 2
        data.bass = float(self._smoothed[:lo].mean()) * 4.0
        data.mid = float(self._smoothed[lo:mid_hi].mean()) * 4.0
        data.treble = float(self._smoothed[mid_hi:].mean()) * 6.0
        data.bass = min(1.0, data.bass)
        data.mid = min(1.0, data.mid)
        data.treble = min(1.0, data.treble)

        # Spectral flux onset detection
        flux = float(
            np.sum(np.maximum(spectrum - self._prev_spectrum, 0.0))
        )
        self._prev_spectrum = spectrum.copy()
        self._flux_history.append(flux)
        if len(self._flux_history) > _ONSET_WINDOW:
            self._flux_history.pop(0)

        if self._beat_cooldown > 0:
            self._beat_cooldown -= 1
            data.beat = 0.0
        else:
            arr = np.array(self._flux_history, dtype=np.float32)
            mean = arr.mean()
            std = arr.std()
            if std > 1e-6 and flux > mean + _BEAT_THRESHOLD * std:
                data.beat = 1.0
                self._beat_cooldown = 10   # 10 frames min between beats
            else:
                data.beat = 0.0

        return data
