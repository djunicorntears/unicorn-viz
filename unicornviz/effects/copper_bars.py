"""
Copper Bars — Amiga-style horizontal raster/color bars.
Each bar is a gradient band whose position oscillates on a sine.
Audio-reactive: bass drives bar spread, beat flashes palette.
"""
from __future__ import annotations

import numpy as np
import moderngl

from unicornviz.effects.base import BaseEffect, AudioData

_VERT = """
#version 330
in vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv = in_vert * 0.5 + 0.5;   // 0..1
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

_FRAG = """
#version 330
uniform float iTime;
uniform float iBass;
uniform float iBeat;
uniform float iSpeed;
in vec2 v_uv;
out vec4 fragColor;

#define NUM_BARS 6

vec3 bar_color(int idx, float phase) {
    // Six classic Amiga colour schemes
    vec3 palette[6];
    palette[0] = vec3(1.0, 0.0, 0.2);   // red
    palette[1] = vec3(0.0, 0.5, 1.0);   // cyan
    palette[2] = vec3(1.0, 0.7, 0.0);   // gold
    palette[3] = vec3(0.2, 1.0, 0.3);   // green
    palette[4] = vec3(0.8, 0.0, 1.0);   // purple
    palette[5] = vec3(0.0, 1.0, 1.0);   // aqua
    return palette[idx] * (0.5 + 0.5 * cos(phase));
}

void main() {
    float y = v_uv.y;
    float t = iTime * iSpeed;
    float spread = 0.12 + iBass * 0.08;

    vec3 col = vec3(0.02);  // dark background

    for (int i = 0; i < NUM_BARS; i++) {
        float fi = float(i) / float(NUM_BARS);
        // Each bar centre oscillates on its own sine
        float center = 0.5
            + sin(t * (0.7 + fi * 0.4) + fi * 2.5) * 0.35
            + sin(t * 0.3 + fi) * 0.1;

        float dist = abs(y - center);
        if (dist < spread) {
            float blend = 1.0 - dist / spread;
            blend = blend * blend * (3.0 - 2.0 * blend); // smoothstep
            vec3 bc = bar_color(i, t * 2.0 + fi * 3.14);
            bc *= 1.0 + iBeat * 0.5;
            col = mix(col, bc, blend);
        }
    }

    // Scanline overlay
    float scan = 0.85 + 0.15 * sin(v_uv.y * 1080.0 * 3.14159);
    col *= scan;

    fragColor = vec4(col, 1.0);
}
"""


class CopperBars(BaseEffect):
    NAME = "Copper Bars"
    AUTHOR = "unicorn-viz"
    TAGS = ["classic", "amiga", "audio"]

    def _init(self) -> None:
        self.parameters = {"speed": 1.0}
        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad()
        self._bass = 0.0
        self._beat = 0.0

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass = audio.bass
        self._beat = max(0.0, self._beat - dt * 4.0)
        if audio.beat > 0.5:
            self._beat = 1.0

    def render(self) -> None:
        self._prog["iTime"].value = self.time
        self._prog["iBass"].value = self._bass
        self._prog["iBeat"].value = self._beat
        self._prog["iSpeed"].value = self.parameters["speed"]
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
