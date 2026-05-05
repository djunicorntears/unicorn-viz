"""
Starfield — two modes: classic 2D parallax + 3D warp-speed tunnel.
Audio-reactive: beat triggers warp burst, bass controls star brightness.
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
    v_uv = in_vert;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

_FRAG = """
#version 330
uniform float iTime;
uniform vec2 iResolution;
uniform float iWarp;     // 0 = normal, 1 = warp speed
uniform float iBass;
uniform float iSpeed;
in vec2 v_uv;
out vec4 fragColor;

// Hash without sin – clean deterministic star positions
float hash(vec2 p) {
    p = fract(p * vec2(234.31, 678.94));
    p += dot(p, p + 34.23);
    return fract(p.x * p.y);
}

// 3D warp tunnel
vec3 warpStar(vec2 uv, float t) {
    float angle = atan(uv.y, uv.x);
    float radius = length(uv);
    float z = fract(t * iSpeed + hash(vec2(angle * 10.0, floor(radius * 40.0))));
    float sz = max(0.0, 1.0 - z);
    float r = sz * radius;
    float brightness = pow(sz, 3.0) * (0.6 + iBass * 0.4);
    float streak = mix(1.0, 0.02, iWarp) * 0.005;
    float spot = 1.0 - smoothstep(0.0, streak + sz * 0.008 * (1.0 + iWarp * 8.0), abs(length(uv) - r));
    return vec3(brightness * spot);
}

void main() {
    vec2 uv = v_uv * vec2(iResolution.x / iResolution.y, 1.0);
    vec3 col = vec3(0.0);

    // Layer 1: dense small stars
    for (int i = 0; i < 3; i++) {
        float layer = float(i) * 0.37;
        col += warpStar(uv + layer, iTime * (0.2 + layer * 0.15));
    }

    col = clamp(col, 0.0, 1.0);
    // Tint: blue-white with warp becoming orange
    vec3 tint = mix(vec3(0.7, 0.85, 1.0), vec3(1.0, 0.6, 0.2), iWarp);
    fragColor = vec4(col * tint, 1.0);
}
"""


class Starfield(BaseEffect):
    NAME = "Starfield"
    AUTHOR = "unicorn-viz"
    TAGS = ["classic", "audio"]

    def _init(self) -> None:
        self.parameters = {"speed": 0.5, "warp": 0.0}
        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad()
        self._bass = 0.0
        self._beat_decay = 0.0

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass = audio.bass
        if audio.beat > 0.5:
            self._beat_decay = 1.0
        self._beat_decay = max(0.0, self._beat_decay - dt * 2.0)
        self.parameters["warp"] = self._beat_decay

    def render(self) -> None:
        self._prog["iTime"].value = self.time
        self._prog["iResolution"].value = (float(self.width), float(self.height))
        self._prog["iWarp"].value = self.parameters["warp"]
        self._prog["iBass"].value = self._bass
        self._prog["iSpeed"].value = self.parameters["speed"]
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
