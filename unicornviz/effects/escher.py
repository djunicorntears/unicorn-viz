"""
Escher — impossible-style tiling corridor illusion.

Audio reactivity:
- bass: depth pulse
- mid: tile morphing
- beat: inversion flashes
"""
from __future__ import annotations

import moderngl

from unicornviz.effects.base import BaseEffect, AudioData

_VERT = """
#version 330
in vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv = in_vert * 0.5 + 0.5;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

_FRAG = """
#version 330
uniform float iTime;
uniform vec2  iResolution;
uniform float iBass;
uniform float iMid;
uniform float iBeat;
uniform float iSpeed;

in vec2 v_uv;
out vec4 fragColor;

mat2 rot(float a) {
    float c = cos(a), s = sin(a);
    return mat2(c, -s, s, c);
}

float box(vec2 p, vec2 b) {
    vec2 d = abs(p) - b;
    return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
}

void main() {
    vec2 uv = v_uv * 2.0 - 1.0;
    uv.x *= iResolution.x / max(iResolution.y, 1.0);

    float t = iTime * (0.35 + iSpeed * 0.8);

    // Pseudo-perspective grid warp for impossible corridor feel.
    float depth = 1.0 / (1.0 + abs(uv.y) * (1.4 + iBass * 1.2));
    vec2 p = uv * depth;
    p = rot(0.25 * sin(t * 0.7)) * p;

    vec2 g = p * (9.0 + iMid * 6.0);
    vec2 id = floor(g);
    vec2 fp = fract(g) - 0.5;

    float tile = step(0.5, fract(id.x * 0.5 + id.y * 0.5));
    float edge = smoothstep(0.08, 0.02, abs(box(fp, vec2(0.42, 0.42))));

    vec3 cA = vec3(0.95, 0.95, 0.90);
    vec3 cB = vec3(0.05, 0.05, 0.08);
    vec3 col = mix(cA, cB, tile);

    // Outline network
    col = mix(col, vec3(0.2, 0.8, 1.0), edge * 0.6);

    // Impossible inversion bands
    float bands = smoothstep(0.4, 0.0, abs(sin((p.x + p.y) * 5.0 + t * 1.4)));
    col = mix(col, 1.0 - col, bands * (0.18 + iBeat * 0.35));

    // Depth vignette
    float vig = smoothstep(1.6, 0.25, length(uv));
    col *= vig;

    fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
"""


class Escher(BaseEffect):
    NAME = "Escher"
    AUTHOR = "unicorn-viz"
    TAGS = ["art", "optical", "audio"]

    def _init(self) -> None:
        self.parameters = {"speed": 1.0}
        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad()
        self._bass = 0.0
        self._mid = 0.0
        self._beat = 0.0

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass = audio.bass
        self._mid = audio.mid
        if audio.beat > 0.5:
            self._beat = 1.0
        self._beat = max(0.0, self._beat - dt * 4.0)

    def render(self) -> None:
        self._prog["iTime"].value = self.time
        self._prog["iResolution"].value = (float(self.width), float(self.height))
        self._prog["iBass"].value = self._bass
        self._prog["iMid"].value = self._mid
        self._prog["iBeat"].value = self._beat
        self._prog["iSpeed"].value = float(self.parameters["speed"])
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
