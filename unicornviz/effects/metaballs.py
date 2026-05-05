"""
Metaballs — GLSL SDF-based orbs that attract/repel each other.
Audio-reactive: bass grows orb radii, beat fires a new orb burst.
"""
from __future__ import annotations

import math
import numpy as np
import moderngl

from unicornviz.effects.base import BaseEffect, AudioData

_NUM_BALLS = 10

_VERT = """
#version 330
in vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv = in_vert * vec2(1.777, 1.0);  // aspect-corrected
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

_FRAG = f"""
#version 330
#define N {_NUM_BALLS}
// Flat float array: ball data packed as x0,y0,r0, x1,y1,r1, ...
uniform float balls[N * 3];
uniform float iTime;
uniform float iBeat;
in vec2 v_uv;
out vec4 fragColor;

vec3 palette(float t) {{
    vec3 a = vec3(0.5, 0.5, 0.5);
    vec3 b = vec3(0.5, 0.5, 0.5);
    vec3 c = vec3(2.0, 1.0, 0.0);
    vec3 d = vec3(0.5, 0.20, 0.25);
    return a + b * cos(6.28318 * (c * t + d));
}}

void main() {{
    float field = 0.0;
    for (int i = 0; i < N; i++) {{
        float bx = balls[i * 3];
        float by = balls[i * 3 + 1];
        float br = balls[i * 3 + 2];
        vec2 d = v_uv - vec2(bx, by);
        field += br * br / max(dot(d, d), 0.0001);
    }}

    float surface = clamp(field - 1.0, 0.0, 1.0);
    float edge = abs(field - 1.2);
    float glow = 1.0 / (1.0 + edge * edge * 80.0);

    vec3 col = palette(field * 0.15 + iTime * 0.05);
    col = mix(vec3(0.0), col, surface);
    col += vec3(0.3, 0.6, 1.0) * glow * (0.4 + iBeat * 0.6);

    col *= 0.9 + 0.1 * sin(gl_FragCoord.y * 3.14159 * 2.0);

    fragColor = vec4(col, 1.0);
}}
"""


class Metaballs(BaseEffect):
    NAME = "Metaballs"
    AUTHOR = "unicorn-viz"
    TAGS = ["classic", "audio"]

    def _init(self) -> None:
        self.parameters = {"speed": 1.0}
        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad()
        # Random phase offsets and orbits for each ball
        rng = np.random.default_rng(42)
        self._phases = rng.uniform(0, math.tau, (_NUM_BALLS, 3))
        self._freqs = rng.uniform(0.3, 1.1, (_NUM_BALLS, 2))
        self._radii = rng.uniform(0.12, 0.22, _NUM_BALLS)
        self._bass = 0.0
        self._beat = 0.0

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass = audio.bass
        if audio.beat > 0.5:
            self._beat = 1.0
        self._beat = max(0.0, self._beat - dt * 3.0)

    def render(self) -> None:
        t = self.time * self.parameters["speed"]
        balls = []
        for i in range(_NUM_BALLS):
            x = math.sin(t * self._freqs[i, 0] + self._phases[i, 0]) * 1.3
            y = math.cos(t * self._freqs[i, 1] + self._phases[i, 1]) * 0.8
            r = self._radii[i] * (1.0 + self._bass * 0.5)
            balls.extend([x, y, r])

        self._prog["iTime"].value = self.time
        self._prog["iBeat"].value = self._beat
        # Set entire float array in one call (moderngl exposes 'balls' not 'balls[0]')
        self._prog["balls"].value = tuple(balls)

        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
