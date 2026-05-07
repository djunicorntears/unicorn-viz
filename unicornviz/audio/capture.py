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


def _candidate_monitor_devices(hint: str, try_alsa: bool = True) -> list[int | None]:
    """Return ordered candidate input devices for auto-fallback probing."""
    if not _SD_AVAILABLE:
        return [None]
    try:
        devices = sd.query_devices()
    except Exception:
        return [None]

    hint_lower = hint.lower()
    if hint_lower:
        matches = [
            i for i, d in enumerate(devices)
            if d.get('max_input_channels', 0) >= 1 and hint_lower in d['name'].lower()
        ]
        return matches or [None]

    app_keywords = ('spotify', 'firefox', 'chrome', 'chromium', 'brave', 'vlc', 'mpv')
    ranked: list[tuple[int, int]] = []
    
    # High priority: ALSA loopback if enabled (stable fallback for OBS recording)
    alsa_found = False
    if try_alsa:
        for i, d in enumerate(devices):
            if d.get('max_input_channels', 0) < 1:
                continue
            name = d['name'].lower()
            if 'loopback' in name:
                ranked.append((0, i))
                alsa_found = True
                log.info("Audio: ALSA loopback device available: %d (%s)", i, d['name'])
    
    # Check for OBS
    obs_found = False
    for i, d in enumerate(devices):
        if d.get('max_input_channels', 0) < 1:
            continue
        name = d['name'].lower()
        if 'obs' in name:
            obs_found = True
            log.info("Audio: OBS detected: device %d (%s)", i, d['name'])
    
    # Rank remaining devices
    for i, d in enumerate(devices):
        if d.get('max_input_channels', 0) < 1:
            continue
        name = d['name'].lower()
        rank = 99
        # Prioritize actual app audio sources (Spotify, web browsers, etc.)
        if any(key in name for key in app_keywords):
            rank = 1 if try_alsa else 0
        # System default fallback
        elif 'pipewire' in name or 'default' in name:
            rank = 2 if try_alsa else 1
        # Generic monitors (but not OBS)
        elif 'monitor' in name and 'obs' not in name:
            rank = 3 if try_alsa else 2
        # Explicit deprecation: OBS monitor should NEVER be auto-selected
        elif 'obs' in name:
            rank = 99
        ranked.append((rank, i))

    ranked.sort()
    candidates = [i for _, i in ranked]
    candidates.append(None)
    return candidates


def _find_monitor_device(hint: str) -> int | None:
    """
    Return device index matching hint, or auto-select best monitor source.

    Auto-select priority (when hint is empty):
      1. OBS virtual monitor (OBS is running and routing desktop audio)
      2. Any PipeWire/PulseAudio monitor sink
      3. None (sounddevice will use the system default input)
    """
    if not _SD_AVAILABLE:
        return None
    try:
        devices = sd.query_devices()
    except Exception:
        return None

    hint_lower = hint.lower()

    # Explicit hint: find first input device whose name contains the hint
    if hint_lower:
        for i, d in enumerate(devices):
            if d.get("max_input_channels", 0) < 1:
                continue
            if hint_lower in d["name"].lower():
                return i
        log.warning("Audio: no device matching %r found, falling back to auto", hint)

    # Auto-detect: prefer OBS monitor (captures desktop audio through OBS)
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) < 1:
            continue
        name = d["name"].lower()
        if "obs" in name and "monitor" in name:
            log.info("Audio: auto-selected OBS monitor device %d (%s)", i, d["name"])
            return i

    # Fall back to any PipeWire/PulseAudio monitor sink
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) < 1:
            continue
        name = d["name"].lower()
        if "monitor" in name:
            log.info("Audio: auto-selected monitor device %d (%s)", i, d["name"])
            return i

    return None


class AudioCapture:
    """
    Runs a sounddevice InputStream in a background thread.
    Call `get_block()` to retrieve the latest PCM block (or None if silent).
    """

    def __init__(
        self,
        device_hint: str = "",
        buffer_seconds: float = 2.0,
        latency: str = "high",
        try_alsa_loopback: bool = True,
    ) -> None:
        self._device_hint = device_hint
        self._buffer_seconds = buffer_seconds
        self._latency = latency
        self._try_alsa_loopback = try_alsa_loopback
        self._sample_rate = _SAMPLE_RATE
        self._channels = _CHANNELS
        self._buf: deque[np.ndarray] = deque(
            maxlen=int(_SAMPLE_RATE * buffer_seconds / _BLOCK_SIZE) + 1
        )
        self._lock = threading.Lock()
        self._stream: "sd.InputStream | None" = None
        self._active = False
        self._candidate_devices: list[int | None] = []
        self._candidate_index = 0
        self._silent_blocks = 0

    def _open_stream(self, device: int | None) -> None:
        native_rate: int = _SAMPLE_RATE
        native_channels: int = _CHANNELS
        if device is not None:
            try:
                info = sd.query_devices(device)
                native_rate = int(info.get('default_samplerate', _SAMPLE_RATE))
                native_channels = min(_CHANNELS, int(info.get('max_input_channels', _CHANNELS)))
            except Exception:
                pass
        else:
            try:
                info = sd.query_devices(kind='input')
                native_rate = int(info.get('default_samplerate', _SAMPLE_RATE))
                native_channels = min(_CHANNELS, int(info.get('max_input_channels', _CHANNELS)))
            except Exception:
                pass

        self._sample_rate = native_rate
        self._channels = native_channels
        new_maxlen = int(native_rate * self._buffer_seconds / _BLOCK_SIZE) + 1
        with self._lock:
            self._buf = deque(maxlen=new_maxlen)
        self._stream = sd.InputStream(
            device=device,
            samplerate=native_rate,
            channels=native_channels,
            blocksize=_BLOCK_SIZE,
            dtype=np.float32,
            callback=self._callback,
            latency=self._latency,
        )
        self._stream.start()
        self._active = True
        self._silent_blocks = 0
        if device is not None:
            dev_name = sd.query_devices(device)['name']
            if 'loopback' in dev_name.lower():
                log.info("Audio capture: using ALSA loopback device %d (%s) at %d Hz", device, dev_name, native_rate)
            else:
                log.info('Audio capture: device %d (%s) at %d Hz (native rate)', device, dev_name, native_rate)
        else:
            log.info('Audio capture: using default input device at %d Hz', native_rate)
        log.info('Audio capture started: %d Hz, %d ch, latency=%s', native_rate, native_channels, self._latency)

    def start(self) -> None:
        if not _SD_AVAILABLE:
            log.info("Audio capture disabled (sounddevice not available)")
            return

        try:
            self._candidate_devices = _candidate_monitor_devices(
                self._device_hint, try_alsa=self._try_alsa_loopback
            )
            self._candidate_index = 0
            self._open_stream(self._candidate_devices[self._candidate_index])
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
        mono = indata.mean(axis=1) if indata.ndim > 1 and indata.shape[1] > 1 else indata[:, 0]
        rms = float(np.sqrt(np.mean(mono * mono)))
        if rms < 0.002:
            self._silent_blocks += 1
        else:
            self._silent_blocks = 0
        with self._lock:
            self._buf.append(mono.copy())

    def maybe_fallback(self) -> None:
        """Switch to next candidate device if current source appears silent."""
        if self._device_hint or len(self._candidate_devices) <= 1:
            return
        silent_time = self._silent_blocks * (_BLOCK_SIZE / max(self._sample_rate, 1))
        if silent_time < 0.8:
            return
        if self._candidate_index + 1 >= len(self._candidate_devices):
            return

        current = self._candidate_devices[self._candidate_index]
        self._candidate_index += 1
        nxt = self._candidate_devices[self._candidate_index]
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            current_name = sd.query_devices(current)['name'] if current is not None else 'None'
            next_name = sd.query_devices(nxt)['name'] if nxt is not None else 'default'
            if nxt is not None and 'loopback' in next_name.lower():
                log.info('Audio capture: fallback from %r to ALSA loopback %d (%s)', current_name, nxt, next_name)
            else:
                log.info('Audio capture: source %r silent, trying fallback %d (%s)', current_name, nxt if nxt is not None else -1, next_name)
            self._open_stream(nxt)
        except Exception as exc:
            log.warning('Audio fallback failed: %s', exc)

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
