"""
Tunnel — classic texture-mapped infinite tunnel.
Audio-reactive: beat pulses radius/twist, bass drives spin speed.
"""
from __future__ import annotations

import numpy as np
import moderngl
from PIL import Image
from pathlib import Path

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
uniform sampler2D tunnel_tex;
uniform float iTime;
uniform float iSpeed;
uniform float iBass;
uniform float iBeat;
in vec2 v_uv;
out vec4 fragColor;

#define PI 3.14159265

void main() {
    vec2 p = v_uv;   // -1..1
    p.x *= 1.777;    // aspect correct

    float dist  = length(p);
    float angle = atan(p.y, p.x) / PI;  // -1..1

    // Tunnel mapping: tex_u = angle, tex_v = 1/dist → scrolling depth
    float depth = 0.3 / (dist + 0.01);
    float twist = iTime * iSpeed * 0.15 + iBass * 0.5;

    vec2 uv = vec2(angle + twist, depth - iTime * iSpeed * 0.4);
    uv.x += iBeat * 0.1;   // beat-snap horizontal shift

    vec3 col = texture(tunnel_tex, uv).rgb;

    // Darken edges (vignette)
    float vig = 1.0 - smoothstep(0.6, 1.2, dist);
    col *= vig;

    // Scanlines
    col *= 0.88 + 0.12 * sin(gl_FragCoord.y * 3.14159 * 2.0);

    fragColor = vec4(col, 1.0);
}
"""


def _make_default_tunnel_texture(ctx: moderngl.Context) -> moderngl.Texture:
    """Generate a procedural brick/grid tunnel texture."""
    W, H = 256, 256
    data = np.zeros((H, W, 3), dtype=np.uint8)
    for y in range(H):
        for x in range(W):
            brick_x = (x + (y // 16) * 8) % 32
            brick_y = y % 16
            in_mortar = brick_x < 2 or brick_y < 2
            if in_mortar:
                data[y, x] = [30, 30, 30]
            else:
                shade = int(120 + 60 * ((x % 32) / 32.0))
                data[y, x] = [shade, shade // 2, shade // 3]
    tex = ctx.texture((W, H), 3, data=data.tobytes())
    tex.filter = moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR
    tex.repeat_x = True
    tex.repeat_y = True
    tex.build_mipmaps()
    return tex


class Tunnel(BaseEffect):
    NAME = "Tunnel"
    AUTHOR = "unicorn-viz"
    TAGS = ["classic", "audio"]

    def _init(self) -> None:
        self.parameters = {"speed": 1.0}
        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad()
        self._bass = 0.0
        self._beat = 0.0

        # Load custom texture if provided
        tex_path = Path(self.config.get("texture", "assets/textures/tunnel.png"))
        if tex_path.exists():
            img = Image.open(tex_path).convert("RGB")
            w, h = img.size
            self._tex = self.ctx.texture((w, h), 3, data=img.tobytes())
            self._tex.filter = moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR
            self._tex.repeat_x = True
            self._tex.repeat_y = True
            self._tex.build_mipmaps()
        else:
            self._tex = _make_default_tunnel_texture(self.ctx)

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass = audio.bass
        if audio.beat > 0.5:
            self._beat = 1.0
        self._beat = max(0.0, self._beat - dt * 4.0)

    def render(self) -> None:
        self._prog["iTime"].value = self.time
        self._prog["iSpeed"].value = self.parameters["speed"]
        self._prog["iBass"].value = self._bass
        self._prog["iBeat"].value = self._beat
        self._tex.use(location=0)
        self._prog["tunnel_tex"].value = 0
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
        self._tex.release()
