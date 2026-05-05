"""
Fire — classic 1D cellular automaton upward propagation.
CPU-side simulation, uploaded as a 2D texture each frame.
Audio-reactive: bass increases heat injection intensity.
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
    // flip Y so fire rises correctly
    v_uv = vec2(in_vert.x * 0.5 + 0.5, 1.0 - (in_vert.y * 0.5 + 0.5));
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

_FRAG = """
#version 330
uniform sampler2D fire_tex;
in vec2 v_uv;
out vec4 fragColor;

vec3 fire_palette(float t) {
    // Black → red → orange → yellow → white
    vec3 c0 = vec3(0.0, 0.0, 0.0);
    vec3 c1 = vec3(0.8, 0.0, 0.0);
    vec3 c2 = vec3(1.0, 0.5, 0.0);
    vec3 c3 = vec3(1.0, 1.0, 0.2);
    vec3 c4 = vec3(1.0, 1.0, 1.0);
    t = clamp(t, 0.0, 1.0);
    if (t < 0.25) return mix(c0, c1, t * 4.0);
    if (t < 0.5)  return mix(c1, c2, (t - 0.25) * 4.0);
    if (t < 0.75) return mix(c2, c3, (t - 0.5) * 4.0);
    return mix(c3, c4, (t - 0.75) * 4.0);
}

void main() {
    float heat = texture(fire_tex, v_uv).r;
    fragColor = vec4(fire_palette(heat), 1.0);
}
"""

# Simulation resolution (independent of display resolution for performance)
_SIM_W = 320
_SIM_H = 200


class Fire(BaseEffect):
    NAME = "Fire"
    AUTHOR = "unicorn-viz"
    TAGS = ["classic", "audio"]

    def _init(self) -> None:
        self.parameters = {"speed": 1.0, "intensity": 0.85}
        self._buf = np.zeros((_SIM_H, _SIM_W), dtype=np.float32)
        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad()
        self._tex = self.ctx.texture((_SIM_W, _SIM_H), 1, dtype="f4")
        self._tex.filter = moderngl.LINEAR, moderngl.LINEAR
        self._bass = 0.0
        self._accum = 0.0

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass = audio.bass
        self._accum += dt * self.parameters["speed"] * 60.0

        steps = int(self._accum)
        self._accum -= steps
        for _ in range(max(1, steps)):
            self._step()

    def _step(self) -> None:
        buf = self._buf
        intensity = self.parameters["intensity"] + self._bass * 0.15

        # Ignite bottom row
        noise = np.random.uniform(0.0, 1.0, _SIM_W).astype(np.float32)
        buf[-1, :] = np.where(noise < intensity, 1.0, buf[-1, :] * 0.95)

        # Propagate upward with cooling
        cooling = np.random.uniform(0.0, 0.04, (_SIM_H, _SIM_W)).astype(np.float32)
        buf[:-1, :] = (
            (
                buf[1:, :]
                + np.roll(buf[1:, :], -1, axis=1)
                + np.roll(buf[1:, :], 1, axis=1)
                + buf[:-1, :]  # slight vertical blur
            )
            * 0.245
            - cooling[:-1, :]
        ).clip(0.0, 1.0)

    def render(self) -> None:
        self._tex.write(self._buf.tobytes())
        self._tex.use(location=0)
        self._prog["fire_tex"].value = 0
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
        self._tex.release()
