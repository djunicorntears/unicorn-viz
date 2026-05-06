"""
Audio Spectrum — frequency bars + oscilloscope waveform.
Two sub-modes cycled with a parameter:
  mode=0  spectrum bars (FFT)
  mode=1  oscilloscope (waveform)
  mode=2  both stacked
"""
from __future__ import annotations

import math
import numpy as np
import moderngl

from unicornviz.effects.base import BaseEffect, AudioData

_VERT_BARS = """
#version 330
in  vec2  in_pos;
in  float in_mag;
in  vec3  in_col;
out float v_mag;
out vec3  v_col;
void main() {
    gl_Position = vec4(in_pos, 0.0, 1.0);
    v_mag = in_mag;
    v_col = in_col;
}
"""

_FRAG_BARS = """
#version 330
in  float v_mag;
in  vec3  v_col;
out vec4  fragColor;
void main() {
    fragColor = vec4(v_col * (0.6 + v_mag * 0.4), 1.0);
}
"""

_VERT_WAVE = """
#version 330
in  vec2 in_pos;
out float v_x;
void main() {
    gl_Position = vec4(in_pos, 0.0, 1.0);
    v_x = in_pos.x;
}
"""

_FRAG_WAVE = """
#version 330
in  float v_x;
out vec4  fragColor;
uniform vec3 uColor;
void main() {
    fragColor = vec4(uColor, 0.9);
}
"""

_VERT_FULL = """
#version 330
in  vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv = in_vert * 0.5 + 0.5;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

_FRAG_RAIN = """
#version 330
uniform float iTime;
uniform float iBass;
uniform float iTreble;
uniform vec2  iResolution;

in  vec2 v_uv;
out vec4 fragColor;

float hash(float n) { return fract(sin(n) * 43758.5453123); }
float hash2(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

// Returns 1 if pixel (col, row) in a character cell is lit
float glyph(vec2 cell, float ch, vec2 frac) {
    // Encode a 4x6 bitmap for 8 pseudo-chars (binary + ACGT)
    // Packed as 24-bit integer patterns; we use hash to vary per cell
    float bit = floor(ch * 8.0);
    // Simple: odd columns lit creates a glyph-like silhouette
    float cx = frac.x;
    float cy = frac.y;
    float v = hash(floor(cx * 4.0) + floor(cy * 6.0) * 4.0 + ch * 97.3 + cell.x * 13.7);
    return step(0.45, v);
}

void main() {
    // Character grid: ~80 cols on a 1920-wide screen
    float charW = iResolution.x / 80.0;
    float charH = charW * 1.5;

    vec2 cell = floor(v_uv * iResolution / vec2(charW, charH));
    vec2 frac = fract(v_uv * iResolution / vec2(charW, charH));

    float col = cell.x;
    float row = cell.y;
    float nRows = iResolution.y / charH;

    // Each column has an offset and speed
    float speed  = 4.0 + hash(col * 7.3) * 10.0 + iBass * 6.0;
    float offset = hash(col * 13.1) * nRows;
    float head   = mod(iTime * speed + offset, nRows * 1.4);

    // Distance below the head
    float dist = head - row;

    if (dist < 0.0 || dist > 18.0) {
        fragColor = vec4(0.0);
        return;
    }

    // Choose cyan or purple column
    float colType = step(0.5, hash(col * 31.7));

    // Brightness falls off below head
    float bright = exp(-dist * 0.25) * (0.8 + iTreble * 0.4);
    // Head pixel extra bright
    if (dist < 1.0) bright = 1.0 + iTreble * 0.6;

    // Changing character: flicker faster near head
    float t = iTime * (2.0 + (1.0 - dist / 18.0) * 6.0);
    float ch = hash2(vec2(col, floor(t)));
    float lit = glyph(cell, ch, frac);

    vec3 cyan    = vec3(0.0, 1.0, 0.95);
    vec3 purple  = vec3(0.75, 0.0, 1.0);
    vec3 tint    = mix(cyan, purple, colType);

    fragColor = vec4(tint * bright * lit, bright * lit * 0.85);
}
"""

_N_BARS = 64
_N_WAVE = 512


def _bar_colour(i: int, n: int) -> tuple[float, float, float]:
    """HSV-like rainbow across bar index."""
    t = i / n
    r = 0.5 + 0.5 * math.sin(t * 6.28 + 0.0)
    g = 0.5 + 0.5 * math.sin(t * 6.28 + 2.09)
    b = 0.5 + 0.5 * math.sin(t * 6.28 + 4.18)
    return r, g, b


class AudioSpectrum(BaseEffect):
    NAME = "Audio Spectrum"
    AUTHOR = "unicorn-viz"
    TAGS = ["audio", "visualizer"]

    def _init(self) -> None:
        self.parameters = {"mode": 2, "glow": 1.0}

        self._rain_prog = self._make_program(_VERT_FULL, _FRAG_RAIN)
        self._rain_vao, self._rain_vbo = self._fullscreen_quad(self._rain_prog)

        self._bar_prog  = self._make_program(_VERT_BARS, _FRAG_BARS)
        self._wave_prog = self._make_program(_VERT_WAVE, _FRAG_WAVE)

        # Pre-allocate to worst-case size so we never orphan and invalidate the VAO
        # Bars: _N_BARS bars × (6 verts/bar + 6 peak verts) × 6 floats × 4 bytes
        bar_bytes = _N_BARS * 12 * 6 * 4
        self._bar_vbo = self.ctx.buffer(reserve=bar_bytes)
        # Wave: _N_WAVE vec2 points × 4 bytes
        wave_bytes = _N_WAVE * 2 * 4
        self._wave_vbo = self.ctx.buffer(reserve=wave_bytes)

        # Explicit format strings: 2f=pos, 1f=mag, 3f=col (24 bytes stride)
        self._bar_vao = self.ctx.vertex_array(
            self._bar_prog,
            [(self._bar_vbo, "2f 1f 3f", "in_pos", "in_mag", "in_col")],
        )
        # Wave: 2f=pos (8 bytes stride)
        self._wave_vao = self.ctx.vertex_array(
            self._wave_prog,
            [(self._wave_vbo, "2f", "in_pos")],
        )

        self._fft  = np.zeros(_N_BARS, dtype=np.float32)
        self._wave = np.zeros(_N_WAVE, dtype=np.float32)
        self._smooth = np.zeros(_N_BARS, dtype=np.float32)
        self._peak   = np.zeros(_N_BARS, dtype=np.float32)
        self._peak_hold = np.zeros(_N_BARS, dtype=np.float32)
        self._bass   = 0.0
        self._treble = 0.0

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass   = audio.bass
        self._treble = audio.treble

        if audio.fft is not None and len(audio.fft) >= _N_BARS:
            raw = audio.fft[:_N_BARS].copy()
        else:
            raw = np.zeros(_N_BARS, dtype=np.float32)

        # Smooth + peak hold
        self._smooth = self._smooth * 0.8 + raw * 0.2
        self._peak_hold = np.maximum(self._peak_hold - dt * 0.4, 0.0)
        new_peaks = self._smooth > self._peak
        self._peak[new_peaks] = self._smooth[new_peaks]
        self._peak_hold[new_peaks] = 1.5
        self._peak = np.where(self._peak_hold > 0, self._peak, self._peak * 0.99)

        if audio.waveform is not None and len(audio.waveform) >= _N_WAVE:
            self._wave = audio.waveform[:_N_WAVE].copy()
        else:
            self._wave = np.zeros(_N_WAVE, dtype=np.float32)

    def _build_bars(self) -> tuple[np.ndarray, int]:
        verts = []
        bar_w = 2.0 / _N_BARS
        for i in range(_N_BARS):
            h = float(self._smooth[i]) * 1.8
            x0 = -1.0 + i * bar_w + bar_w * 0.05
            x1 = x0 + bar_w * 0.90
            y0 = -1.0
            y1 = -1.0 + h
            r, g, b = _bar_colour(i, _N_BARS)
            mag = float(self._smooth[i])
            # 2 triangles per bar
            for x, y in [(x0,y0),(x1,y0),(x0,y1),(x1,y0),(x1,y1),(x0,y1)]:
                verts += [x, y, mag, r, g, b]
            # Peak dot
            py = -1.0 + float(self._peak[i]) * 1.8 + 0.01
            for x, y in [(x0,py),(x1,py),(x0,py+0.008),(x1,py),(x1,py+0.008),(x0,py+0.008)]:
                verts += [x, y, 1.0, 1.0, 1.0, 1.0]
        arr = np.array(verts, dtype=np.float32)
        return arr, len(arr) // 6

    def _build_waveform(self, y_base: float, y_scale: float) -> tuple[np.ndarray, int]:
        xs = np.linspace(-1.0, 1.0, _N_WAVE, dtype=np.float32)
        ys = y_base + self._wave * y_scale
        verts = np.column_stack([xs, ys])
        return verts.astype(np.float32), len(verts)

    def render(self) -> None:
        mode = int(self.parameters["mode"]) % 3
        self.ctx.clear(0.0, 0.0, 0.0, 1.0)

        # Matrix rain background (additive blend ON)
        self.ctx.enable(moderngl.BLEND)
        self._rain_prog["iTime"].value       = self.time
        self._rain_prog["iBass"].value       = self._bass
        self._rain_prog["iTreble"].value     = self._treble
        self._rain_prog["iResolution"].value = (float(self.width), float(self.height))
        self._rain_vao.render(moderngl.TRIANGLE_STRIP)

        if mode in (0, 2):
            bar_data, n_bar_verts = self._build_bars()
            if bar_data.nbytes <= self._bar_vbo.size:
                self._bar_vbo.write(bar_data)
                self._bar_vao.render(moderngl.TRIANGLES, vertices=n_bar_verts)

        if mode in (1, 2):
            y_base  = 0.0 if mode == 1 else -0.5
            y_scale = 0.8 if mode == 1 else 0.4
            wave_data, n_wave = self._build_waveform(y_base, y_scale)
            if wave_data.nbytes <= self._wave_vbo.size:
                self._wave_vbo.write(wave_data)
                self._wave_prog["uColor"].value = (0.3, 1.0, 0.8)
                self._wave_vao.render(moderngl.LINE_STRIP, vertices=n_wave)

    def destroy(self) -> None:
        self._rain_vao.release()
        self._rain_vbo.release()
        self._rain_prog.release()
        self._bar_vao.release()
        self._wave_vao.release()
        self._bar_vbo.release()
        self._wave_vbo.release()
        self._bar_prog.release()
        self._wave_prog.release()
