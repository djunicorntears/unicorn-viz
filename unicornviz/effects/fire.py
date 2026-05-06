"""
Fire — GPU ping-pong fluid fire simulation.

Two off-screen FBOs alternate each frame.  A "simulate" shader evolves
the heat field (diffuse/advect upward/cool); a "render" shader maps heat
to a vivid multi-colour palette.  The bottom edge is ignited each frame
by a noise bar whose intensity scales with bass.

Audio reactivity:
  - bass   → ignition intensity + ember scatter
  - beat   → instantaneous heat spike across the whole base
  - treble → adds fast flicker to the flame tips
"""
from __future__ import annotations

import numpy as np
import moderngl

from unicornviz.effects.base import BaseEffect, AudioData

# Simulation runs at this resolution; displayed fullscreen via bilinear up-scale
_SIM_W = 480
_SIM_H = 270

# ---------------------------------------------------------------------------
# Shaders
# ---------------------------------------------------------------------------

_VERT = """
#version 330
in vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv        = in_vert * 0.5 + 0.5;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

# Simulation step: read previous heat field, diffuse + advect + cool
_SIM_FRAG = """
#version 330
uniform sampler2D prev;
uniform vec2      iResolution;   // sim resolution
uniform float     iBass;
uniform float     iBeat;
uniform float     iTreble;
uniform float     iTime;
uniform float     iIntensity;
// Simple hash for noise
float hash(vec2 p) {
    p = fract(p * vec2(127.1, 311.7));
    p += dot(p, p + 19.19);
    return fract(p.x * p.y);
}
out vec4 fragColor;
in  vec2 v_uv;

void main() {
    vec2 px = 1.0 / iResolution;

    // Sample neighbourhood with upward advection
    float lift = px.y * (1.35 + iBass * 0.9);
    float c  = texture(prev, v_uv).r;
    float u  = texture(prev, v_uv + vec2( 0.0,  lift)).r;
    float ul = texture(prev, v_uv + vec2(-px.x, lift)).r;
    float ur = texture(prev, v_uv + vec2( px.x, lift)).r;
    float l  = texture(prev, v_uv + vec2(-px.x, 0.0 )).r;
    float r  = texture(prev, v_uv + vec2( px.x, 0.0 )).r;

    // Weighted diffuse + advect
    float heat = (u * 1.8 + ul * 0.8 + ur * 0.8 + l * 0.3 + r * 0.3 + c * 0.8) / 4.8;

    // Cooling
    float cool = 0.006 + iTreble * 0.004;
    heat = max(0.0, heat - cool);

    // Bottom ignition strip
    float ignY = 10.0 * px.y;
    if (v_uv.y < ignY) {
        float n = hash(vec2(v_uv.x * 73.1, iTime * 0.3));
        float n2 = hash(vec2(v_uv.x * 17.9, iTime * 0.17 + 5.3));
        float base = iIntensity + iBass * 0.55 + iBeat * 0.75;
        heat = mix(heat, clamp(base * (0.7 + 0.3 * n), 0.0, 1.0),
                   0.55 + 0.35 * n2);
    }

    fragColor = vec4(heat, 0.0, 0.0, 1.0);
}
"""

# Display: map heat → vivid multi-stop palette
_DISPLAY_FRAG = """
#version 330
uniform sampler2D heat_tex;
uniform float     iBass;
uniform float     iBeat;
uniform float     iTime;

in  vec2 v_uv;
out vec4 fragColor;

vec3 palette(float t) {
    // 6-stop: black → deep violet → red → orange → yellow → white
    t = clamp(t, 0.0, 1.0);
    vec3 stops[6];
    stops[0] = vec3(0.00, 0.00, 0.00);
    stops[1] = vec3(0.20, 0.00, 0.30);
    stops[2] = vec3(0.85, 0.05, 0.00);
    stops[3] = vec3(1.00, 0.45, 0.00);
    stops[4] = vec3(1.00, 0.95, 0.10);
    stops[5] = vec3(1.00, 1.00, 1.00);
    float s = t * 5.0;
    int i   = int(s);
    float f = fract(s);
    if (i >= 5) return stops[5];
    return mix(stops[i], stops[i+1], f);
}

void main() {
    // Flip Y for display (heat sims bottom ignition)
    vec2 uv = vec2(v_uv.x, 1.0 - v_uv.y);
    float heat = texture(heat_tex, uv).r;

    // Chromatic embellishment: slight hue warp on bass
    float hShift = iBass * 0.08 * sin(uv.x * 12.0 + iTime * 2.0);
    heat = clamp(heat + hShift, 0.0, 1.0);

    vec3 col = palette(heat);

    // Beat bloom: briefly brighten
    col += iBeat * 0.25 * vec3(1.0, 0.6, 0.3);

    fragColor = vec4(clamp(col, 0.0, 1.5), 1.0);
}
"""


class Fire(BaseEffect):
    """GPU ping-pong fluid fire with vivid palette and full audio reactivity."""

    NAME = "Fire"
    AUTHOR = "unicorn-viz"
    TAGS = ["classic", "audio", "gpu"]

    def _init(self) -> None:
        self.parameters = {"intensity": 0.82, "speed": 1.0}

        self._sim_prog  = self._make_program(_VERT, _SIM_FRAG)
        self._disp_prog = self._make_program(_VERT, _DISPLAY_FRAG)

        self._sim_vao, self._vbo = self._fullscreen_quad(self._sim_prog)
        self._disp_vao = self.ctx.vertex_array(
            self._disp_prog,
            [(self._vbo, "2f", "in_vert")],
        )

        # Two ping-pong FBOs at sim resolution
        def _make_sim_fbo() -> tuple[moderngl.Framebuffer, moderngl.Texture]:
            tex = self.ctx.texture((_SIM_W, _SIM_H), 4, dtype="f2")
            tex.filter = moderngl.LINEAR, moderngl.LINEAR
            tex.repeat_x = False
            tex.repeat_y = False
            fbo = self.ctx.framebuffer(color_attachments=[tex])
            # Seed with zeros
            fbo.clear(0.0, 0.0, 0.0, 1.0)
            return fbo, tex

        self._fbo_a, self._tex_a = _make_sim_fbo()
        self._fbo_b, self._tex_b = _make_sim_fbo()
        self._ping = True   # True = read B write A; False = read A write B

        self._bass   = 0.0
        self._beat   = 0.0
        self._treble = 0.0

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass   = audio.bass
        self._treble = audio.treble
        if audio.beat > 0.5:
            self._beat = 1.0
        self._beat = max(0.0, self._beat - dt * 5.0)

    def render(self) -> None:
        ctx = self.ctx
        spd  = self.parameters["speed"]
        target_fbo = ctx.fbo

        # --- Simulation step(s) ---
        # Multiple sub-steps per frame gives taller, fuller flames.
        steps = max(2, int(4 * spd))
        for _ in range(steps):
            if self._ping:
                read_tex, write_fbo = self._tex_b, self._fbo_a
            else:
                read_tex, write_fbo = self._tex_a, self._fbo_b
            self._ping = not self._ping

            write_fbo.use()
            ctx.viewport = (0, 0, _SIM_W, _SIM_H)
            read_tex.use(location=0)
            self._sim_prog["prev"].value       = 0
            self._sim_prog["iResolution"].value = (float(_SIM_W), float(_SIM_H))
            self._sim_prog["iBass"].value      = self._bass * spd
            self._sim_prog["iBeat"].value      = self._beat
            self._sim_prog["iTreble"].value    = self._treble
            self._sim_prog["iTime"].value      = self.time
            self._sim_prog["iIntensity"].value = float(self.parameters["intensity"])
            self._sim_vao.render(moderngl.TRIANGLE_STRIP)

        # --- Display ---
        # Render to whichever target app.py currently has bound (screen or transition FBO).
        if target_fbo is not None and hasattr(target_fbo, "use"):
            target_fbo.use()
        elif ctx.screen is not None:
            ctx.screen.use()
        ctx.viewport = (0, 0, self.width, self.height)
        # The texture we just wrote into is the current heat field
        if self._ping:
            self._tex_b.use(location=0)
        else:
            self._tex_a.use(location=0)
        self._disp_prog["heat_tex"].value = 0
        self._disp_prog["iBass"].value    = self._bass
        self._disp_prog["iBeat"].value    = self._beat
        self._disp_prog["iTime"].value    = self.time
        self._disp_vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._sim_vao.release()
        self._disp_vao.release()
        self._vbo.release()
        self._sim_prog.release()
        self._disp_prog.release()
        self._fbo_a.release()
        self._fbo_b.release()
        self._tex_a.release()
        self._tex_b.release()
