"""
Splash screen rendered before the main effect loop begins.

Loads ``images/unicorn-viz-01.png`` (or any path passed to the constructor),
uploads it as an RGBA GL texture, and renders it fullscreen with a smooth:

  - 0.6 s fade-in
  - hold until ``duration`` seconds total have elapsed
  - 0.8 s fade-out

The splash is also dismissed immediately on Space or any key press.

Usage (called from App.run() before the main loop)::

    splash = Splash(ctx, width, height, "images/unicorn-viz-01.png")
    splash.run(window)   # blocks until done; returns True if app should quit
    splash.destroy()
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

import moderngl
import numpy as np

log = logging.getLogger(__name__)

_FADE_IN  = 0.6   # seconds
_FADE_OUT = 0.8   # seconds

_VERT = """
#version 330
in  vec2 in_vert;
out vec2 v_uv;
void main() {
    // Standard fullscreen quad: UV (0,0)=bottom-left, (1,1)=top-right
    // Map screen top-left to UV (0,1) so image renders right-side-up
    v_uv = vec2(in_vert.x * 0.5 + 0.5, 0.5 - in_vert.y * 0.5);
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

_FRAG = """
#version 330
uniform sampler2D splash_tex;
uniform float     alpha;
uniform float     pulse;
uniform float     hue_time;
in  vec2 v_uv;
out vec4 fragColor;
void main() {
    vec4 col = texture(splash_tex, v_uv);

    // Subtle audio-reactive tint + bloom pulse.
    vec3 tint = vec3(
        0.5 + 0.5 * sin(hue_time + 0.0),
        0.5 + 0.5 * sin(hue_time + 2.09),
        0.5 + 0.5 * sin(hue_time + 4.18)
    );
    vec3 rgb = col.rgb;
    float luma = dot(rgb, vec3(0.2126, 0.7152, 0.0722));
    float hi = smoothstep(0.42, 0.9, luma); // tint highlights more than shadows

    // Balanced bloom and tinting (between subtle and dramatic).
    rgb *= 1.0 + pulse * 0.40;
    rgb = mix(rgb, rgb * (0.86 + 0.14 * tint), clamp(pulse * 0.44 * hi, 0.0, 0.45));
    rgb += vec3(0.10) * pulse * hi;

    fragColor = vec4(clamp(rgb, 0.0, 1.0), col.a * alpha);
}
"""


class Splash:
    """Fullscreen splash screen with fade-in / fade-out."""

    def __init__(
        self,
        ctx: moderngl.Context,
        width: int,
        height: int,
        image_path: str | Path = "images/unicorn-viz-01.png",
        duration: float = 4.0,
        bass_supplier: Callable[[], float] | None = None,
    ) -> None:
        self._ctx = ctx
        self._width = width
        self._height = height
        self._duration = duration
        self._done = False
        self._bass_supplier = bass_supplier
        self._pulse = 0.0
        self._peak_audio = 0.0  # Track max audio level seen

        self._prog = ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)

        verts = np.array([-1, -1, -1, 1, 1, -1, 1, 1], dtype=np.float32)
        vbo = ctx.buffer(verts)
        self._vao = ctx.simple_vertex_array(self._prog, vbo, "in_vert")
        self._vbo = vbo

        self._tex = self._load_texture(Path(image_path))

    def _load_texture(self, path: Path) -> moderngl.Texture:
        """Load PNG via Pillow and upload as RGBA texture."""
        try:
            from PIL import Image
            img = Image.open(path).convert("RGBA")
            # Scale to window size, preserving aspect ratio with letterbox
            img_w, img_h = img.size
            win_w, win_h = self._width, self._height
            scale = min(win_w / img_w, win_h / img_h)
            new_w = int(img_w * scale)
            new_h = int(img_h * scale)

            # Resize and paste onto a black background
            resized = img.resize((new_w, new_h), Image.LANCZOS)
            canvas = Image.new("RGBA", (win_w, win_h), (0, 0, 0, 255))
            x_off = (win_w - new_w) // 2
            y_off = (win_h - new_h) // 2
            canvas.paste(resized, (x_off, y_off))

            # Flip vertically for OpenGL (origin is bottom-left in GL textures)
            # The vert shader maps v_uv.y = 0.5 - in_vert.y * 0.5, which already
            # accounts for the GL convention — do NOT flip the image here.
            # canvas = canvas.transpose(Image.FLIP_TOP_BOTTOM)

            tex = self._ctx.texture((win_w, win_h), 4, data=canvas.tobytes())
            tex.filter = moderngl.LINEAR, moderngl.LINEAR
            log.info("Splash: loaded %s (%dx%d)", path, img_w, img_h)
            return tex
        except Exception as exc:
            log.warning("Splash: could not load %s: %s — using blank", path, exc)
            blank = bytes([0, 0, 0, 0])
            return self._ctx.texture((1, 1), 4, data=blank)

    def run(self, window: object) -> bool:
        """
        Block until the splash finishes or the user presses any key.

        Parameters
        ----------
        window:
            The SDL2 window pointer (passed to ``SDL_GL_SwapWindow``).

        Returns
        -------
        bool
            True if the app should quit (e.g. the user pressed Escape).
        """
        import sdl2

        start = time.perf_counter()
        quit_requested = False

        ctx = self._ctx

        while True:
            now  = time.perf_counter()
            elapsed = now - start

            # Input handling — any key skips / Esc quits
            event = sdl2.SDL_Event()
            while sdl2.SDL_PollEvent(event):
                if event.type == sdl2.SDL_QUIT:
                    quit_requested = True
                    self._done = True
                elif event.type == sdl2.SDL_KEYDOWN:
                    if event.key.keysym.sym == sdl2.SDLK_ESCAPE:
                        quit_requested = True
                    self._done = True

            # Pull audio each frame (if available) and smooth into pulse.
            bass = 0.0
            if self._bass_supplier is not None:
                try:
                    bass = float(self._bass_supplier())
                    self._peak_audio = max(self._peak_audio, bass)
                except Exception as e:
                    log.debug(f"Splash bass supplier error: {e}")
                    bass = 0.0
            self._pulse = self._pulse * 0.80 + max(0.0, bass) * 0.20
            if elapsed < 0.5 and int(elapsed * 60) % 6 == 0:  # Log first few frames
                log.info(f"Splash frame: elapsed={elapsed:.2f}s, bass={bass:.3f}, pulse={self._pulse:.3f}")

            if self._done or elapsed >= self._duration:
                # Final frame at alpha 0 so there's no pop
                self._render(0.0, 0.0, elapsed * 1.5)
                sdl2.SDL_GL_SwapWindow(window)
                break

            # Compute alpha from fade curve
            if elapsed < _FADE_IN:
                alpha = elapsed / _FADE_IN
            elif elapsed < self._duration - _FADE_OUT:
                alpha = 1.0
            else:
                remaining = self._duration - elapsed
                alpha = max(0.0, remaining / _FADE_OUT)

            self._render(alpha, self._pulse, elapsed * 1.5)
            sdl2.SDL_GL_SwapWindow(window)
            sdl2.SDL_Delay(16)   # ~60 fps cap

        return quit_requested

    def _render(self, alpha: float, pulse: float, hue_time: float) -> None:
        ctx = self._ctx
        ctx.screen.use()
        ctx.viewport = (0, 0, self._width, self._height)
        ctx.clear(0.0, 0.0, 0.0, 1.0)
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self._tex.use(location=0)
        self._prog["splash_tex"].value = 0
        self._prog["alpha"].value = float(alpha)
        self._prog["pulse"].value = float(max(0.0, min(1.0, pulse)))
        self._prog["hue_time"].value = float(hue_time)
        self._vao.render(moderngl.TRIANGLE_STRIP)

    @property
    def had_audio(self) -> bool:
        """Whether significant audio was detected during splash."""
        return self._peak_audio > 0.15
        """Called if the window is resized during the splash."""
        self._width = width
        self._height = height

    def destroy(self) -> None:
        """Release all GL resources."""
        self._tex.release()
        self._vao.release()
        self._vbo.release()
        self._prog.release()
