"""
ANSI Viewer — loads .ANS files from assets/ansi/, renders them with a
CRT/phosphor glow post-processing shader.  Scrolls through files on the
playlist and supports slow auto-scroll within tall art.

Audio-reactive:
  - beat flashes the phosphor glow
  - bass slightly warps the CRT curvature
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import moderngl

from unicornviz.effects.base import BaseEffect, AudioData
from unicornviz.ansi.loader import ANSIParser
from unicornviz.ansi.font import build_font_atlas
from unicornviz.ansi.renderer import canvas_to_texture

log = logging.getLogger(__name__)

# ── Vertex / fragment shaders ─────────────────────────────────────────────────

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
uniform sampler2D ansi_tex;
uniform float     iTime;
uniform float     iScroll;   // vertical scroll 0..1
uniform float     iBass;
uniform float     iBeat;
uniform float     iGlow;     // 0 = no glow, 1 = full CRT phosphor
uniform float     iCRT;      // 0 = flat, 1 = full barrel distortion
uniform vec2      iResolution;

in  vec2 v_uv;
out vec4 fragColor;

// Barrel distortion
vec2 crt_uv(vec2 uv) {
    vec2 cc = uv * 2.0 - 1.0;
    float dist = dot(cc, cc);
    float warp = iCRT * (1.0 + iBass * 0.05);
    cc *= 1.0 + dist * warp * 0.1;
    return cc * 0.5 + 0.5;
}

void main() {
    // Scroll: shift v coordinate
    vec2 uv = v_uv;
    uv.y = fract(uv.y + iScroll);

    // CRT barrel warp
    vec2 cuv = crt_uv(uv);

    // Clamp — show black outside art
    if (cuv.x < 0.0 || cuv.x > 1.0 || cuv.y < 0.0 || cuv.y > 1.0) {
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    vec3 col = texture(ansi_tex, cuv).rgb;

    // Scanlines — emulate phosphor rows
    float scan = 1.0 - 0.18 * sin(cuv.y * iResolution.y * 3.14159 * 2.0);
    col *= scan;

    // Phosphor glow — sample neighbours
    if (iGlow > 0.01) {
        vec2 px = vec2(1.0) / iResolution;
        vec3 glow =
            texture(ansi_tex, cuv + vec2( px.x * 2.0, 0.0)).rgb * 0.15 +
            texture(ansi_tex, cuv + vec2(-px.x * 2.0, 0.0)).rgb * 0.15 +
            texture(ansi_tex, cuv + vec2(0.0,  px.y * 2.0)).rgb * 0.10 +
            texture(ansi_tex, cuv + vec2(0.0, -px.y * 2.0)).rgb * 0.10;
        col += glow * iGlow * (1.0 + iBeat * 0.8);
    }

    // Vignette
    vec2 vc = cuv * 2.0 - 1.0;
    float vig = 1.0 - dot(vc, vc) * 0.25;
    col *= vig;

    // Slight green phosphor tint for CRT feel
    col.g = mix(col.g, col.g * 1.05, iCRT * 0.3);

    // Overall brightness flash on beat
    col *= 1.0 + iBeat * 0.15;

    fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
"""


class ANSIViewer(BaseEffect):
    NAME = "ANSI Viewer"
    AUTHOR = "unicorn-viz"
    TAGS = ["ansi", "classic", "audio"]

    def _init(self) -> None:
        self.parameters = {
            "speed":     1.0,   # scroll speed multiplier
            "glow":      0.6,   # phosphor glow intensity
            "crt":       0.7,   # CRT barrel distortion
            "slide_time": 15.0, # seconds per file
        }

        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad()

        self._font_atlas = build_font_atlas(self.ctx)
        self._parser = ANSIParser()

        # Load all .ANS files from configured directory
        ansi_dir = Path(self.config.get("ansi_dir", "assets/ansi"))
        self._files = sorted(ansi_dir.glob("*.ans")) + sorted(ansi_dir.glob("*.ANS"))
        if not self._files:
            log.warning("No .ANS files found in %s", ansi_dir)
            self._files = []

        self._file_idx = 0
        self._ansi_tex: moderngl.Texture | None = None
        self._scroll = 0.0
        self._slide_timer = 0.0
        self._bass = 0.0
        self._beat = 0.0
        self._title = ""

        self._load_current()

    def _load_current(self) -> None:
        if not self._files:
            self._ansi_tex = self._make_fallback_tex()
            self._title = "No .ANS files found"
            return

        path = self._files[self._file_idx % len(self._files)]
        try:
            raw = path.read_bytes()
            canvas = self._parser.parse(raw)
            if self._ansi_tex is not None:
                self._ansi_tex.release()
            self._ansi_tex = canvas_to_texture(self.ctx, canvas, self._font_atlas)
            info = getattr(canvas, "_sauce", {})
            title = info.get("title", "") or path.stem
            self._title = title
            log.info("ANSI Viewer loaded: %s (%dx%d)", path.name, canvas.width, canvas.height)
        except Exception as exc:
            log.warning("Failed to load %s: %s", path, exc)
            self._ansi_tex = self._make_fallback_tex()
            self._title = f"Error: {path.name}"
        self._scroll = 0.0

    def _make_fallback_tex(self) -> moderngl.Texture:
        """1×1 black texture as placeholder."""
        tex = self.ctx.texture((1, 1), 4, data=bytes([0, 0, 0, 255]))
        return tex

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass = audio.bass
        if audio.beat > 0.5:
            self._beat = 1.0
        self._beat = max(0.0, self._beat - dt * 4.0)

        # Scroll within current file
        self._scroll += dt * 0.012 * self.parameters["speed"]
        self._scroll %= 1.0

        # Advance to next file
        self._slide_timer += dt
        if self._slide_timer >= self.parameters["slide_time"] and self._files:
            self._slide_timer = 0.0
            self._file_idx = (self._file_idx + 1) % len(self._files)
            self._load_current()

    def render(self) -> None:
        if self._ansi_tex is None:
            return
        self._prog["iTime"].value = self.time
        self._prog["iScroll"].value = self._scroll
        self._prog["iBass"].value = self._bass
        self._prog["iBeat"].value = self._beat
        self._prog["iGlow"].value = self.parameters["glow"]
        self._prog["iCRT"].value  = self.parameters["crt"]
        self._prog["iResolution"].value = (float(self.width), float(self.height))
        self._ansi_tex.use(location=0)
        self._prog["ansi_tex"].value = 0
        self._vao.render(moderngl.TRIANGLE_STRIP)

    @property
    def current_title(self) -> str:
        return self._title

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
        self._font_atlas.release()
        if self._ansi_tex is not None:
            self._ansi_tex.release()
