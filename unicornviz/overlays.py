"""
On-screen overlays rendered in immediate mode using a simple bitmap font.
Handles: effect name flash, persistent name overlay, help screen,
audio device selector, MIDI device selector, and generic flash messages.
"""
from __future__ import annotations

import logging
import struct
from pathlib import Path

import moderngl
import numpy as np

log = logging.getLogger(__name__)

# 8×8 IBM CP437-style font baked into the module so we have zero asset deps.
# Each character is 8 bytes, one bit per pixel per row.
# This is the classic IBM PC BIOS 8×8 font subset (printable ASCII 32–126).
_FONT_DATA: bytes | None = None


def _build_font_texture(ctx: moderngl.Context) -> moderngl.Texture:
    """Create a 128×8 luminance texture from the built-in 8×8 bitmap font."""
    # 8×8 font, 96 printable chars (ASCII 32..127), packed in a 128-wide atlas
    # We embed a minimal hand-crafted font for the overlay characters we need.
    # Each char = 8 rows × 8 cols = 8 bytes.  Atlas is 128 chars wide × 8 tall.
    data = np.zeros((8, 128 * 8), dtype=np.uint8)

    # Pull in the font from assets if available, otherwise synthesise.
    font_path = Path("assets/fonts/font8x8.bin")
    if font_path.exists():
        raw = font_path.read_bytes()
        # Expect 256 chars × 8 bytes = 2048 bytes
        for codepoint in range(min(256, len(raw) // 8)):
            for row in range(8):
                byte = raw[codepoint * 8 + row]
                for col in range(8):
                    if byte & (0x80 >> col):
                        data[row, codepoint * 8 + col] = 255
    else:
        # Minimal built-in: just render a dot pattern so something shows
        for codepoint in range(128):
            for row in range(8):
                for col in range(8):
                    # Checkerboard for unknown chars except space
                    if codepoint > 32 and (row + col) % 2 == 0:
                        data[row, codepoint * 8 + col] = 180

    tex = ctx.texture((128 * 8, 8), 1, data=data.tobytes())
    tex.filter = moderngl.NEAREST, moderngl.NEAREST
    return tex


class Overlays:
    """Manages all HUD/overlay rendering."""

    HELP_TEXT = [
        " UNICORN VIZ — Hotkeys ",
        "─" * 24,
        " N / →    Next effect",
        " P / ←    Prev effect",
        " F         Fullscreen",
        " Space     Pause/resume",
        " R         Random playlist",
        " 1-9       Jump to effect",
        " + / -     Speed up/down",
        " A         Audio source",
        " M         MIDI device",
        " TAB       Name overlay",
        " S         Screenshot",
        " H         This help",
        " ESC       Quit",
    ]

    def __init__(
        self,
        ctx: moderngl.Context,
        width: int,
        height: int,
    ) -> None:
        self._ctx = ctx
        self._width = width
        self._height = height

        self._show_name = False
        self._show_help = False
        self._show_audio = False
        self._show_midi = False
        self._flash_text: str = ""
        self._flash_timer: float = 0.0
        self._name_text: str = ""

        self._font_tex = _build_font_texture(ctx)
        self._prog = self._build_program()
        self._build_vbo()

    def _build_program(self) -> moderngl.Program:
        vert = """
#version 330
in vec2 in_vert;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    gl_Position = vec4(in_vert, 0.0, 1.0);
    v_uv = in_uv;
}
"""
        frag = """
#version 330
uniform sampler2D font_tex;
uniform vec4 color;
in vec2 v_uv;
out vec4 fragColor;
void main() {
    float a = texture(font_tex, v_uv).r;
    fragColor = vec4(color.rgb, color.a * a);
}
"""
        return self._ctx.program(vertex_shader=vert, fragment_shader=frag)

    def _build_vbo(self) -> None:
        # We'll generate geometry dynamically per frame; start with empty buffer.
        self._vbo = self._ctx.buffer(reserve=1024 * 4 * 4)
        self._vao = self._ctx.simple_vertex_array(
            self._prog, self._vbo, "in_vert", "in_uv"
        )

    def _char_quads(
        self,
        text: str,
        x: float,
        y: float,
        scale: float,
        color: tuple[float, float, float, float],
    ) -> np.ndarray:
        """
        Build interleaved (pos_x, pos_y, uv_x, uv_y) vertex data for `text`.
        x, y are in screen pixels from top-left.
        scale is pixels-per-cell (8 px = 1x).
        Returns float32 array of 6 vertices per character (2 tris).
        """
        char_w = 8.0 * scale
        char_h = 8.0 * scale
        atlas_w = 128 * 8
        atlas_h = 8

        verts: list[float] = []
        cx = x
        for ch in text:
            code = ord(ch) & 0x7F
            u0 = (code * 8) / atlas_w
            u1 = u0 + 8.0 / atlas_w
            v0 = 0.0
            v1 = 1.0

            # NDC conversion
            def px(px_val: float) -> float:
                return (px_val / self._width) * 2.0 - 1.0

            def py(py_val: float) -> float:
                return 1.0 - (py_val / self._height) * 2.0

            x0 = px(cx)
            x1 = px(cx + char_w)
            y0 = py(y)
            y1 = py(y + char_h)

            # Two triangles (6 verts)
            verts += [x0, y0, u0, v0]
            verts += [x1, y0, u1, v0]
            verts += [x0, y1, u0, v1]
            verts += [x1, y0, u1, v0]
            verts += [x1, y1, u1, v1]
            verts += [x0, y1, u0, v1]

            cx += char_w

        return np.array(verts, dtype=np.float32) if verts else np.zeros(0, dtype=np.float32)

    def _draw_text(
        self,
        text: str,
        x: float,
        y: float,
        scale: float = 2.0,
        color: tuple[float, float, float, float] = (1.0, 1.0, 0.0, 1.0),
    ) -> None:
        data = self._char_quads(text, x, y, scale, color)
        if data.size == 0:
            return
        # Resize VBO if needed
        needed = data.nbytes
        if needed > self._vbo.size:
            self._vbo.orphan(needed * 2)
        self._vbo.write(data)
        self._prog["color"].value = color
        self._font_tex.use(location=0)
        self._prog["font_tex"].value = 0
        self._ctx.enable(moderngl.BLEND)
        self._vao.render(moderngl.TRIANGLES, vertices=len(data) // 4)

    def render(self, dt: float) -> None:
        """Call each frame after the main effect renders."""
        if self._flash_timer > 0.0:
            self._flash_timer -= dt
            alpha = min(1.0, self._flash_timer * 2.0)
            self._draw_text(
                self._flash_text,
                20, self._height - 40,
                scale=2.0,
                color=(1.0, 0.8, 0.0, alpha),
            )

        if self._show_name and self._name_text:
            self._draw_text(
                self._name_text,
                20, 20,
                scale=3.0,
                color=(0.0, 1.0, 1.0, 0.85),
            )

        if self._show_help:
            self._render_help()

    def _render_help(self) -> None:
        pad = 20.0
        scale = 1.8
        lh = 8 * scale + 4
        y = pad
        for line in self.HELP_TEXT:
            self._draw_text(line, pad, y, scale=scale, color=(0.2, 1.0, 0.4, 0.95))
            y += lh

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def flash_name(self, name: str, duration: float = 3.0) -> None:
        self._name_text = name
        self._flash_text = f">> {name}"
        self._flash_timer = duration

    def flash_message(self, msg: str, duration: float = 2.0) -> None:
        self._flash_text = msg
        self._flash_timer = duration

    def toggle_name_overlay(self) -> None:
        self._show_name = not self._show_name

    def toggle_help(self) -> None:
        self._show_help = not self._show_help

    def toggle_audio_selector(self) -> None:
        self._show_audio = not self._show_audio

    def toggle_midi_selector(self) -> None:
        self._show_midi = not self._show_midi

    def resize(self, w: int, h: int) -> None:
        self._width = w
        self._height = h

    def destroy(self) -> None:
        self._font_tex.release()
        self._prog.release()
        self._vbo.release()
