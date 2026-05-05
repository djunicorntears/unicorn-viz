# Unicorn Viz — Configuration Reference

All settings live in `config.toml` in the project root.

---

## `[window]`

| Key          | Type    | Default        | Description                                |
|--------------|---------|----------------|--------------------------------------------|
| `width`      | int     | `1920`         | Initial window width in pixels             |
| `height`     | int     | `1080`         | Initial window height in pixels            |
| `fullscreen` | bool    | `false`        | Start in fullscreen mode                   |
| `title`      | str     | `"Unicorn Viz"`| Window title bar text                      |

---

## `[demo]`

| Key                  | Type   | Default        | Description                                         |
|----------------------|--------|----------------|-----------------------------------------------------|
| `mode`               | str    | `"sequential"` | Playlist mode: `"sequential"` or `"random"`         |
| `effect_duration`    | int    | `20`           | Seconds before auto-advancing to the next effect    |
| `transition`         | str    | `"crossfade"`  | Transition type: `"cut"`, `"crossfade"`, `"scanwipe"` |
| `transition_duration`| float  | `1.0`          | Transition length in seconds                        |

---

## `[audio]`

| Key              | Type   | Default | Description                                                  |
|------------------|--------|---------|--------------------------------------------------------------|
| `device`         | str    | `""`    | Device name substring (empty = auto-detect PipeWire monitor) |
| `fft_bands`      | int    | `512`   | Number of FFT frequency bins                                 |
| `buffer_seconds` | float  | `2.0`   | Audio ring buffer length in seconds                          |

---

## `[midi]`

| Key      | Type | Default | Description                                            |
|----------|------|---------|--------------------------------------------------------|
| `device` | str  | `""`    | MIDI port name substring (empty = first available port)|

---

## `[ansi]`

| Key        | Type | Default            | Description                                                        |
|------------|------|--------------------|--------------------------------------------------------------------|
| `ansi_dir` | str  | `"assets/ansi"`    | Directory (or comma-separated list) containing `.ans` / `.ANS` files |

---

## `[effects]`

Per-effect parameter overrides.  Keyed by **Python class name**.

```toml
[effects.Plasma]
speed = 2.0

[effects.ANSIViewer]
slide_time = 30.0
glow       = 0.8
crt        = 0.5

[effects.FractalZoom]
max_iter = 120

[effects.ParticleStorm]
speed = 1.5
```

Available parameters per effect:

| Effect            | Parameter   | Range      | Meaning                         |
|-------------------|-------------|------------|---------------------------------|
| All               | `speed`     | 0.05–10.0  | Animation rate multiplier       |
| ANSIViewer        | `glow`      | 0.0–1.0    | Phosphor glow intensity         |
| ANSIViewer        | `crt`       | 0.0–1.0    | CRT barrel distortion strength  |
| ANSIViewer        | `slide_time`| 5.0–300.0  | Seconds per art piece           |
| AudioSpectrum     | `mode`      | 0, 1, 2    | 0=bars, 1=waveform, 2=both      |
| AudioSpectrum     | `glow`      | 0.0–1.0    | Bar glow                        |
| FractalZoom       | `max_iter`  | 32–512     | Iteration depth                 |

---

## `[playlist]`

| Key        | Type           | Default | Description                                               |
|------------|----------------|---------|-----------------------------------------------------------|
| `sequence` | list of str    | `[]`    | Ordered list of effect class names; empty = all effects   |

Example — only rotate through three effects:

```toml
[playlist]
sequence = ["Plasma", "Fire", "Starfield"]
```
