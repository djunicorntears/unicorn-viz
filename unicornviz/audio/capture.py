"""
Audio capture via sounddevice (PipeWire/PulseAudio loopback monitor).
Feeds a ring buffer consumed by the analyzer on the main thread.
"""
from __future__ import annotations

import logging
import threading
from collections import deque

import numpy as np

log = logging.getLogger(__name__)

try:
    import sounddevice as sd
    _SD_AVAILABLE = True
except Exception as e:
    log.warning("sounddevice unavailable: %s — audio disabled", e)
    _SD_AVAILABLE = False

_SAMPLE_RATE = 48000   # PipeWire default; 44100 fallback attempted at runtime
_BLOCK_SIZE = 1024
_CHANNELS = 2


def _find_monitor_device(hint: str) -> int | None:
    """Return device index of a monitor/loopback source matching hint."""
    if not _SD_AVAILABLE:
        return None
    try:
        devices = sd.query_devices()
    except Exception:
        return None
    hint_lower = hint.lower()
    for i, d in enumerate(devices):
        name = d["name"].lower()
        max_in = d.get("max_input_channels", 0)
        if max_in < 1:
            continue
        # PipeWire monitor sinks have "monitor" in their name
        if hint_lower and hint_lower in name:
            return i
        if not hint_lower and "monitor" in name:
            return i
    # Fallback: default input
    return None


class AudioCapture:
    """
    Runs a sounddevice InputStream in a background thread.
    Call `get_block()` to retrieve the latest PCM block (or None if silent).
    """

    def __init__(self, device_hint: str = "", buffer_seconds: float = 2.0) -> None:
        self._device_hint = device_hint
        self._buffer_seconds = buffer_seconds
        self._sample_rate = _SAMPLE_RATE   # updated in start() once device is known
        self._buf: deque[np.ndarray] = deque(
            maxlen=int(_SAMPLE_RATE * buffer_seconds / _BLOCK_SIZE) + 1
        )
        self._lock = threading.Lock()
        self._stream: "sd.InputStream | None" = None
        self._active = False

    def start(self) -> None:
        if not _SD_AVAILABLE:
            log.info("Audio capture disabled (sounddevice not available)")
            return

        device = _find_monitor_device(self._device_hint)
        if device is not None:
            log.info(
                "Audio capture: device %d (%s)",
                device,
                sd.query_devices(device)["name"],
            )
        else:
            log.info("Audio capture: using default input device")

        try:
            # Use the device's native default sample rate when available.
            # PipeWire monitor sinks usually run at 48000 Hz; some at 44100.
            native_rate: int = _SAMPLE_RATE
            if device is not None:
                try:
                    info = sd.query_devices(device)
                    native_rate = int(info.get("default_samplerate", _SAMPLE_RATE))
                except Exception:
                    pass
            elif device is None:
                try:
                    info = sd.query_devices(kind="input")
                    native_rate = int(info.get("default_samplerate", _SAMPLE_RATE))
                except Exception:
                    pass

            self._sample_rate = native_rate
            # Resize ring buffer to match actual sample rate
            new_maxlen = int(native_rate * self._buffer_seconds / _BLOCK_SIZE) + 1
            with self._lock:
                self._buf = deque(maxlen=new_maxlen)
            self._stream = sd.InputStream(
                device=device,
                samplerate=native_rate,
                channels=_CHANNELS,
                blocksize=_BLOCK_SIZE,
                dtype=np.float32,
                callback=self._callback,
                latency="low",
            )
            self._stream.start()
            self._active = True
            log.info("Audio capture started at %d Hz", native_rate)
        except Exception as exc:
            log.warning("Could not open audio stream: %s", exc)

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status,
    ) -> None:
        if status:
            log.debug("Audio status: %s", status)
        mono = indata.mean(axis=1)              # stereo → mono
        with self._lock:
            self._buf.append(mono.copy())

    def get_block(self) -> np.ndarray | None:
        with self._lock:
            if not self._buf:
                return None
            return self._buf[-1]

    def get_history(self, n_blocks: int) -> np.ndarray:
        """Return the last n_blocks concatenated as a single float32 array."""
        with self._lock:
            blocks = list(self._buf)[-n_blocks:]
        if not blocks:
            return np.zeros(_BLOCK_SIZE * n_blocks, dtype=np.float32)
        return np.concatenate(blocks)

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def block_size(self) -> int:
        return _BLOCK_SIZE
