"""
Particle Storm — GPU-simulated particle system using transform feedback.
100k particles driven by curl noise, audio-reactive:
  - Bass increases emission rate & speed
  - Beat triggers a radial blast
  - Treble shifts colour temperature
"""
from __future__ import annotations

import random
import numpy as np
import moderngl

from unicornviz.effects.base import BaseEffect, AudioData

_NUM_PARTICLES = 100_000

# Transform feedback update shader — runs on GPU
_UPDATE_VERT = """
#version 330
in  vec2 in_pos;
in  vec2 in_vel;
in  float in_life;
in  float in_seed;

out vec2  out_pos;
out vec2  out_vel;
out float out_life;
out float out_seed;

uniform float dt;
uniform float iTime;
uniform float iBass;
uniform float iBeat;
uniform vec2  iOrigin;

// Hash-based RNG
float rng(float seed) {
    return fract(sin(seed * 127.1 + iTime * 0.001) * 43758.5453);
}

// 2D curl noise (gradient of rotated noise)
vec2 curl(vec2 p) {
    float e = 0.01;
    float nx0 = sin(p.x * 3.7 + sin(p.y * 2.3 + iTime));
    float nx1 = sin((p.x+e) * 3.7 + sin(p.y * 2.3 + iTime));
    float ny0 = sin(p.y * 3.1 + sin(p.x * 2.7 + iTime * 0.8));
    float ny1 = sin((p.y+e) * 3.1 + sin(p.x * 2.7 + iTime * 0.8));
    return vec2((ny1-ny0)/e, -(nx1-nx0)/e) * 0.3;
}

void main() {
    float life = in_life - dt;

    if (life <= 0.0) {
        // Respawn at origin with random velocity
        float angle = rng(in_seed) * 6.28318;
        float spd   = rng(in_seed + 1.3) * 0.8 + 0.1 + iBass * 0.5;
        float burst  = iBeat * 2.0;
        out_pos  = iOrigin;
        out_vel  = vec2(cos(angle), sin(angle)) * (spd + burst);
        out_life = rng(in_seed + 2.7) * 2.0 + 0.5;
        out_seed = rng(in_seed + 99.9);
    } else {
        vec2 force = curl(in_pos * 0.8) * (1.0 + iBass * 1.5);
        force += vec2(0.0, 0.15);        // slight upward drift
        force -= in_vel * 0.4;           // drag

        out_vel  = in_vel + force * dt;
        out_pos  = in_pos + out_vel * dt;
        out_life = life;
        out_seed = in_seed;
    }
}
"""

# Render shader — point sprites
_RENDER_VERT = """
#version 330
in  vec2  in_pos;
in  float in_life;

uniform vec2  iResolution;
uniform float iTreble;
uniform float iBass;

out float v_life;
out vec3  v_col;

void main() {
    v_life = in_life;

    // Map [-1,1] pos → screen NDC
    gl_Position = vec4(in_pos, 0.0, 1.0);
    // Life-based point size
    float sz = (in_life * 2.0 + iBass * 3.0) * (iResolution.y / 600.0);
    gl_PointSize = clamp(sz, 1.0, 8.0);

    // Colour: hot core (white) → orange → dark red based on life
    float t = clamp(in_life * 0.5, 0.0, 1.0) + iTreble * 0.2;
    v_col = mix(vec3(0.1, 0.0, 0.0),
                mix(vec3(1.0, 0.4, 0.0), vec3(1.0, 1.0, 0.8), t * 0.5),
                t);
}
"""

_RENDER_FRAG = """
#version 330
in  float v_life;
in  vec3  v_col;
out vec4  fragColor;

void main() {
    // Circular sprite
    vec2 uv = gl_PointCoord * 2.0 - 1.0;
    float r = dot(uv, uv);
    if (r > 1.0) discard;
    float alpha = (1.0 - r) * clamp(v_life, 0.0, 1.0);
    fragColor = vec4(v_col, alpha * 0.85);
}
"""


class ParticleStorm(BaseEffect):
    NAME = "Particle Storm"
    AUTHOR = "unicorn-viz"
    TAGS = ["futuristic", "audio", "particles"]

    def _init(self) -> None:
        self.parameters = {"speed": 1.0}
        self._bass = 0.0
        self._treble = 0.0
        self._beat = 0.0

        rng = np.random.default_rng(1337)
        pos  = rng.uniform(-1.0, 1.0, (_NUM_PARTICLES, 2)).astype(np.float32)
        vel  = rng.uniform(-0.2, 0.2, (_NUM_PARTICLES, 2)).astype(np.float32)
        life = rng.uniform( 0.0, 2.5, _NUM_PARTICLES).astype(np.float32)
        seed = rng.uniform( 0.0, 1.0, _NUM_PARTICLES).astype(np.float32)

        data = np.hstack([pos, vel, life[:, None], seed[:, None]]).astype(np.float32)
        # VBO A and B for ping-pong
        self._vbo_a = self.ctx.buffer(data.tobytes())
        self._vbo_b = self.ctx.buffer(data.tobytes())

        # Transform feedback program
        self._update_prog = self.ctx.program(
            vertex_shader=_UPDATE_VERT,
            varyings=["out_pos", "out_vel", "out_life", "out_seed"],
        )
        # Render program
        self._render_prog = self.ctx.program(
            vertex_shader=_RENDER_VERT,
            fragment_shader=_RENDER_FRAG,
        )

        self._stride = 6 * 4   # 6 floats per particle

        def make_update_vao(src: moderngl.Buffer) -> moderngl.VertexArray:
            return self.ctx.vertex_array(
                self._update_prog,
                [(src, "2f 2f 1f 1f", "in_pos", "in_vel", "in_life", "in_seed")],
            )

        def make_render_vao(src: moderngl.Buffer) -> moderngl.VertexArray:
            # Buffer layout: pos(2f) vel(2f) life(1f) seed(1f)
            # Skip vel(2f) and seed(1f) with padding ('x' = skip bytes)
            return self.ctx.vertex_array(
                self._render_prog,
                [(src, "2f 2x4 1f", "in_pos", "in_life")],
            )

        self._update_vao_a = make_update_vao(self._vbo_a)
        self._update_vao_b = make_update_vao(self._vbo_b)
        self._render_vao_a = make_render_vao(self._vbo_a)
        self._render_vao_b = make_render_vao(self._vbo_b)

        self._ping = True   # True = read A write B, False = read B write A
        self._origin = (0.0, 0.0)

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass = audio.bass
        self._treble = audio.treble
        if audio.beat > 0.5:
            self._beat = 1.0
            self._origin = (random.uniform(-0.6, 0.6), random.uniform(-0.5, 0.5))
        self._beat = max(0.0, self._beat - dt * 3.5)

        # Run transform feedback update pass
        dt_scaled = dt * self.parameters["speed"]
        self._update_prog["dt"].value = dt_scaled
        self._update_prog["iTime"].value = self.time
        self._update_prog["iBass"].value = self._bass
        self._update_prog["iBeat"].value = self._beat
        self._update_prog["iOrigin"].value = self._origin

        src_vao = self._update_vao_a if self._ping else self._update_vao_b
        dst_vbo = self._vbo_b if self._ping else self._vbo_a

        # moderngl 5.x transform feedback
        src_vao.transform(dst_vbo, moderngl.POINTS, vertices=_NUM_PARTICLES)

        self._ping = not self._ping

    def render(self) -> None:
        self.ctx.enable(moderngl.BLEND | moderngl.PROGRAM_POINT_SIZE)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE   # additive blend

        self._render_prog["iResolution"].value = (float(self.width), float(self.height))
        self._render_prog["iTreble"].value = self._treble
        self._render_prog["iBass"].value = self._bass

        # Read from the buffer that was just written to
        render_vao = self._render_vao_b if self._ping else self._render_vao_a
        render_vao.render(moderngl.POINTS, vertices=_NUM_PARTICLES)

        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    def destroy(self) -> None:
        for obj in [
            self._update_vao_a, self._update_vao_b,
            self._render_vao_a, self._render_vao_b,
            self._vbo_a, self._vbo_b,
            self._update_prog, self._render_prog,
        ]:
            obj.release()
