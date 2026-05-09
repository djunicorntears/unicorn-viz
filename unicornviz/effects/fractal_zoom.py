"""
Fractal Zoom — Mandelbrot set with smooth colouring and audio-reactive zoom.
Beat triggers a zoom burst; bass shifts the palette; treble adds iteration depth.
"""
from __future__ import annotations

import math
import moderngl
import numpy as np

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
uniform vec2  iResolution;
uniform float iCenterX;
uniform float iCenterY;
uniform float iZoom;
uniform float iPalShift;
uniform float iBass;
uniform float iRotation;
uniform int   iMaxIter;

in  vec2 v_uv;
out vec4 fragColor;

vec3 palette(float t) {
    vec3 a = vec3(0.5, 0.5, 0.5);
    vec3 b = vec3(0.5, 0.5, 0.5);
    vec3 c = vec3(1.0, 1.0, 0.5);
    vec3 d = vec3(0.8, 0.9, 0.3);
    return a + b * cos(6.28318 * (c * t + d));
}

void main() {
    vec2 uv = v_uv * vec2(iResolution.x / iResolution.y, 1.0);
    
    // Apply rotation to the uv coordinates
    float c = cos(iRotation);
    float s = sin(iRotation);
    uv = vec2(c * uv.x - s * uv.y, s * uv.x + c * uv.y);
    
    vec2 centre = vec2(iCenterX, iCenterY);
    vec2 cplx = centre + uv / iZoom;

    vec2 z = vec2(0.0);
    float smooth_iter = 0.0;
    int i;
    for (i = 0; i < iMaxIter; i++) {
        z = vec2(z.x*z.x - z.y*z.y, 2.0*z.x*z.y) + cplx;
        if (dot(z, z) > 256.0) {
            smooth_iter = float(i) - log2(log2(dot(z, z)));
            break;
        }
    }

    if (i == iMaxIter) {
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    float t = smooth_iter / float(iMaxIter) + iPalShift + iBass * 0.1;
    vec3 col = palette(t);
    
    // If stuck at max iterations, show a subtle dark gradient instead of pure black
    if (i == iMaxIter) {
        vec2 dist = abs(uv - vec2(0.5)) * 2.0;
        float d = length(dist);
        col = mix(vec3(0.02), vec3(0.08, 0.05, 0.12), smoothstep(2.0, 0.5, d));
    }
    
    fragColor = vec4(col, 1.0);
}
"""


# Interesting Mandelbrot zoom targets
_TARGETS = [
    (-0.7269,    0.1889),    # Seahorse valley
    (-0.5251993,  0.5260),   # Elephant valley  
    (-0.74543,   0.11301),   # Deep spiral
    (-1.2561,    0.3820),    # Bulb boundary
    (0.2806,     0.5338),    # Mini-brot cluster
    (-0.8614678, 0.2325938), # Glynn valley
]


class FractalZoom(BaseEffect):
    NAME = "Fractal Zoom"
    AUTHOR = "unicorn-viz"
    TAGS = ["futuristic", "audio", "psychedelic"]

    def _init(self) -> None:
        self.parameters = {"speed": 1.0, "max_iter": 180}
        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad()

        # Randomize initial state so we never see the same fractal startup
        self._target_idx = int(self.rng.integers(0, len(_TARGETS)))
        self._cx, self._cy = _TARGETS[self._target_idx]
        # Start with randomized zoom in valid range to avoid black screen
        self._zoom = float(self.rng.uniform(0.4, 0.9))
        self._zoom_vel = 1.0   # zoom multiplier per second
        self._pal_shift = 0.0
        self._rotation = float(self.rng.uniform(-math.pi, math.pi))
        self._bass = 0.0
        self._beat_zoom = 0.0

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass = audio.bass

        if audio.beat > 0.5:
            self._beat_zoom = 2.5    # burst multiplier
        self._beat_zoom = max(1.0, self._beat_zoom - dt * 3.0)

        speed = self.parameters["speed"] * self._beat_zoom
        self._zoom *= math.exp(dt * 0.18 * speed)  # Slower zoom for mesmerizing effect
        self._pal_shift = (self._pal_shift + dt * 0.04 * speed) % 1.0  # Slower color shift
        self._rotation += dt * 0.12 * speed  # Much slower rotation for contemplation

        # Jump to next target when zoomed too deep (precision limit ~1e13)
        if self._zoom > 1e10:
            self._zoom = float(self.rng.uniform(0.5, 0.95))  # Randomize zoom on reset
            self._target_idx = (self._target_idx + 1) % len(_TARGETS)
            self._cx, self._cy = _TARGETS[self._target_idx]
            # Randomize target center slightly within a local region for variety
            self._cx += float(self.rng.uniform(-0.05, 0.05))
            self._cy += float(self.rng.uniform(-0.05, 0.05))
            self._rotation = float(self.rng.uniform(-math.pi, math.pi))  # Fresh rotation

    def render(self) -> None:
        self._prog["iResolution"].value = (float(self.width), float(self.height))
        self._prog["iCenterX"].value  = float(self._cx)
        self._prog["iCenterY"].value  = float(self._cy)
        self._prog["iZoom"].value = float(self._zoom)
        self._prog["iPalShift"].value = self._pal_shift
        self._prog["iBass"].value = self._bass
        self._prog["iRotation"].value = float(self._rotation)
        self._prog["iMaxIter"].value = int(self.parameters["max_iter"]
                                           + audio_iter_boost(self._bass))
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()


def audio_iter_boost(bass: float) -> float:
    return bass * 30
