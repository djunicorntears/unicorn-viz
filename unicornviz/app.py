"""
Main application — SDL2 window (Wayland-first) + moderngl context + main loop.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Type

import moderngl
import numpy as np

# Wayland-first, fall back to x11 automatically
if "SDL_VIDEODRIVER" not in os.environ:
    os.environ["SDL_VIDEODRIVER"] = "wayland"

import sdl2
import sdl2.ext

from unicornviz.config import Config
from unicornviz.effects.base import AudioData, BaseEffect
from unicornviz.effects.registry import get_effects
from unicornviz.audio.manager import AudioManager
from unicornviz.playlist import Playlist
from unicornviz.overlays import Overlays
from unicornviz.hotkeys import HotkeyHandler
from unicornviz.midi import MidiManager

log = logging.getLogger(__name__)

TARGET_FPS = 60
FRAME_TIME = 1.0 / TARGET_FPS


class App:
    def __init__(self, config_path: str = "config.toml") -> None:
        self.cfg = Config(config_path)
        self._running = False
        self._paused = False
        self._ctx: moderngl.Context | None = None
        self._window = None
        self._gl_context = None
        self._current_effect: BaseEffect | None = None
        self._next_effect: BaseEffect | None = None
        self._transition_t: float = 0.0
        self._transition_duration: float = self.cfg.get(
            "demo", "transition_duration", default=1.0
        )
        self._fbo_a: moderngl.Framebuffer | None = None
        self._fbo_b: moderngl.Framebuffer | None = None
        self._blend_prog: moderngl.Program | None = None
        self._blend_vao: moderngl.VertexArray | None = None
        self._width = self.cfg.get("window", "width", default=1920)
        self._height = self.cfg.get("window", "height", default=1080)
        self._fullscreen = self.cfg.get("window", "fullscreen", default=False)
        self._audio = AudioData()

    # ------------------------------------------------------------------ #
    # SDL2 + moderngl init                                                 #
    # ------------------------------------------------------------------ #

    def _init_sdl(self) -> None:
        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_EVENTS) != 0:
            # Wayland may have failed — retry with x11
            os.environ["SDL_VIDEODRIVER"] = "x11"
            if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_EVENTS) != 0:
                raise RuntimeError(
                    f"SDL_Init failed: {sdl2.SDL_GetError().decode()}"
                )
            log.info("Wayland init failed — using x11")
        else:
            log.info(
                "SDL video driver: %s",
                sdl2.SDL_GetCurrentVideoDriver().decode(),
            )

        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_MAJOR_VERSION, 3)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_MINOR_VERSION, 3)
        sdl2.SDL_GL_SetAttribute(
            sdl2.SDL_GL_CONTEXT_PROFILE_MASK, sdl2.SDL_GL_CONTEXT_PROFILE_CORE
        )
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_DOUBLEBUFFER, 1)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_DEPTH_SIZE, 24)

        flags = sdl2.SDL_WINDOW_OPENGL | sdl2.SDL_WINDOW_RESIZABLE
        if self._fullscreen:
            flags |= sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP

        title = self.cfg.get("window", "title", default="Unicorn Viz")
        self._window = sdl2.SDL_CreateWindow(
            title.encode(),
            sdl2.SDL_WINDOWPOS_CENTERED,
            sdl2.SDL_WINDOWPOS_CENTERED,
            self._width,
            self._height,
            flags,
        )
        if not self._window:
            raise RuntimeError(
                f"SDL_CreateWindow failed: {sdl2.SDL_GetError().decode()}"
            )

        self._gl_context = sdl2.SDL_GL_CreateContext(self._window)
        if not self._gl_context:
            raise RuntimeError(
                f"SDL_GL_CreateContext failed: {sdl2.SDL_GetError().decode()}"
            )
        sdl2.SDL_GL_SetSwapInterval(1)  # vsync

        # After fullscreen is applied the OS may give us a different size.
        # Query the actual drawable size and update width/height.
        w_ptr = sdl2.SDL_GetWindowSize.__doc__ and None  # just for type inference
        import ctypes
        w_i = ctypes.c_int(0)
        h_i = ctypes.c_int(0)
        sdl2.SDL_GetWindowSize(self._window, w_i, h_i)
        if self._fullscreen:
            self._width  = w_i.value or self._width
            self._height = h_i.value or self._height
            log.info("Fullscreen drawable size: %dx%d", self._width, self._height)

    def _init_moderngl(self) -> None:
        self._ctx = moderngl.create_context()
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        log.info("OpenGL %s", self._ctx.info["GL_VERSION"])
        self._build_blend_pipeline()

    def _build_blend_pipeline(self) -> None:
        """FBO-pair + crossfade shader used for transitions."""
        self._fbo_a = self._make_fbo()
        self._fbo_b = self._make_fbo()

        vert = """
#version 330
in vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv = in_vert * 0.5 + 0.5;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""
        frag = """
#version 330
uniform sampler2D tex_a;
uniform sampler2D tex_b;
uniform float t;
in vec2 v_uv;
out vec4 fragColor;
void main() {
    fragColor = mix(texture(tex_a, v_uv), texture(tex_b, v_uv), t);
}
"""
        self._blend_prog = self._ctx.program(
            vertex_shader=vert, fragment_shader=frag
        )
        verts = np.array([-1, -1, -1, 1, 1, -1, 1, 1], dtype=np.float32)
        vbo = self._ctx.buffer(verts)
        self._blend_vao = self._ctx.vertex_array(
            self._blend_prog, [(vbo, "2f", "in_vert")]
        )
        self._blend_vbo = vbo  # keep ref so it's not GC'd

    def _make_fbo(self) -> moderngl.Framebuffer:
        tex = self._ctx.texture((self._width, self._height), 4)
        tex.filter = moderngl.LINEAR, moderngl.LINEAR
        depth = self._ctx.depth_renderbuffer((self._width, self._height))
        return self._ctx.framebuffer(color_attachments=[tex], depth_attachment=depth)

    # ------------------------------------------------------------------ #
    # Effect management                                                    #
    # ------------------------------------------------------------------ #

    def _instantiate(self, cls: Type[BaseEffect]) -> BaseEffect:
        effect_cfg = self.cfg.get("effects", cls.__name__, default={})
        if not isinstance(effect_cfg, dict):
            effect_cfg = {}
        # Inject top-level [ansi] config into ANSIViewer so it finds the art dir
        if cls.__name__ == "ANSIViewer":
            ansi_dir = self.cfg.get("ansi", "ansi_dir", default="assets/ansi")
            effect_cfg = {"ansi_dir": str(ansi_dir), **effect_cfg}
        return cls(self._ctx, self._width, self._height, effect_cfg)

    def _switch_effect(self, cls: Type[BaseEffect]) -> None:
        """Begin transition to a new effect."""
        if self._next_effect is not None:
            self._next_effect.destroy()
        self._next_effect = self._instantiate(cls)
        self._transition_t = 0.0

    # ------------------------------------------------------------------ #
    # Main loop                                                            #
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s [%(name)s] %(message)s",
        )
        self._init_sdl()
        self._init_moderngl()

        # Splash screen — shown before any effect loads
        splash_path = self.cfg.get("splash", "image", default="images/unicorn-viz-01.png")
        splash_duration = float(self.cfg.get("splash", "duration", default=4.0))
        if Path(splash_path).exists():
            from unicornviz.splash import Splash
            splash = Splash(
                self._ctx, self._width, self._height,
                image_path=splash_path,
                duration=splash_duration,
            )
            if splash.run(self._window):
                # User pressed Esc during splash — quit immediately
                splash.destroy()
                sdl2.SDL_GL_DeleteContext(self._gl_context)
                sdl2.SDL_DestroyWindow(self._window)
                sdl2.SDL_Quit()
                return
            splash.destroy()

        # Subsystems
        audio_manager = AudioManager(self.cfg)
        audio_manager.start()

        midi_device_hint = self.cfg.get("midi", "device", default="")
        midi_manager = MidiManager(device_hint=midi_device_hint)
        midi_manager.start()
        self._midi_manager = midi_manager

        effects = get_effects()
        if not effects:
            raise RuntimeError("No effects found — check unicornviz/effects/")

        playlist = Playlist(effects, self.cfg)
        overlays = Overlays(self._ctx, self._width, self._height)
        hotkeys = HotkeyHandler(
            app=self,
            playlist=playlist,
            overlays=overlays,
            audio_manager=audio_manager,
        )
        hotkeys.attach_midi(midi_manager)

        # Load first effect
        self._current_effect = self._instantiate(playlist.current())
        self._running = True

        prev_time = time.perf_counter()
        demo_timer = 0.0
        effect_duration = self.cfg.get("demo", "effect_duration", default=20)

        while self._running:
            now = time.perf_counter()
            dt = min(now - prev_time, 0.1)  # cap at 100 ms to avoid spiral
            prev_time = now

            # Poll events
            event = sdl2.SDL_Event()
            while sdl2.SDL_PollEvent(event):
                if event.type == sdl2.SDL_QUIT:
                    self._running = False
                elif event.type == sdl2.SDL_KEYDOWN:
                    hotkeys.handle(event.key.keysym.sym, event.key.keysym.mod)
                elif event.type == sdl2.SDL_WINDOWEVENT:
                    if event.window.event == sdl2.SDL_WINDOWEVENT_RESIZED:
                        self._on_resize(
                            event.window.data1, event.window.data2
                        )

            # Dispatch pending MIDI events to active effect
            if hasattr(self, "_midi_manager"):
                pass   # MidiManager uses a callback thread; forward via action hooks

            # Auto-playlist advance
            if not self._paused and self._next_effect is None:
                allow_advance = True
                try:
                    from unicornviz.effects.ansi_viewer import ANSIViewer
                    if isinstance(self._current_effect, ANSIViewer):
                        allow_advance = self._current_effect.reached_bottom
                except Exception:
                    pass

                demo_timer += dt
                if demo_timer >= effect_duration and allow_advance:
                    demo_timer = 0.0
                    next_cls = playlist.advance()
                    self._switch_effect(next_cls)

            # Update audio
            self._audio = audio_manager.get_audio_data()

            # Update effects
            if not self._paused:
                if self._current_effect:
                    self._current_effect.update(dt, self._audio)
                if self._next_effect:
                    self._next_effect.update(dt, self._audio)

            # If current effect is ANSIViewer, sync its art title to the overlay
            try:
                from unicornviz.effects.ansi_viewer import ANSIViewer
                if isinstance(self._current_effect, ANSIViewer):
                    overlays._name_text = self._current_effect.current_title
            except Exception:
                pass

            # Render
            self._render()
            overlays.render(dt)

            sdl2.SDL_GL_SwapWindow(self._window)

        # Cleanup
        audio_manager.stop()
        midi_manager.stop()
        if self._current_effect:
            self._current_effect.destroy()
        if self._next_effect:
            self._next_effect.destroy()
        overlays.destroy()
        sdl2.SDL_GL_DeleteContext(self._gl_context)
        sdl2.SDL_DestroyWindow(self._window)
        sdl2.SDL_Quit()

    def _render(self) -> None:
        ctx = self._ctx
        transition = self.cfg.get("demo", "transition", default="crossfade")

        if self._next_effect is None:
            # No transition — render current directly to screen
            ctx.screen.use()
            ctx.viewport = (0, 0, self._width, self._height)
            ctx.clear(0.0, 0.0, 0.0, 1.0)
            if self._current_effect:
                self._current_effect.render()
        else:
            # Transition in progress
            self._transition_t += (
                (1.0 / self._transition_duration)
                * (1.0 / TARGET_FPS)
            )
            if self._transition_t >= 1.0 or transition == "cut":
                # Finish transition
                if self._current_effect:
                    self._current_effect.destroy()
                self._current_effect = self._next_effect
                self._next_effect = None
                ctx.screen.use()
                ctx.viewport = (0, 0, self._width, self._height)
                ctx.clear(0.0, 0.0, 0.0, 1.0)
                if self._current_effect:
                    self._current_effect.render()
            elif transition == "crossfade":
                # Render A into FBO a
                self._fbo_a.use()
                ctx.viewport = (0, 0, self._width, self._height)
                ctx.clear(0.0, 0.0, 0.0, 1.0)
                self._current_effect.render()

                # Render B into FBO b
                self._fbo_b.use()
                ctx.clear(0.0, 0.0, 0.0, 1.0)
                self._next_effect.render()

                # Blend to screen
                ctx.screen.use()
                ctx.viewport = (0, 0, self._width, self._height)
                ctx.clear(0.0, 0.0, 0.0, 1.0)
                self._fbo_a.color_attachments[0].use(location=0)
                self._fbo_b.color_attachments[0].use(location=1)
                self._blend_prog["tex_a"].value = 0
                self._blend_prog["tex_b"].value = 1
                self._blend_prog["t"].value = self._transition_t
                self._blend_vao.render(moderngl.TRIANGLE_STRIP)
            else:
                # scanwipe — vertical wipe
                self._fbo_a.use()
                ctx.viewport = (0, 0, self._width, self._height)
                ctx.clear(0.0, 0.0, 0.0, 1.0)
                self._current_effect.render()
                self._fbo_b.use()
                ctx.clear(0.0, 0.0, 0.0, 1.0)
                self._next_effect.render()
                # Fall back to crossfade for scanwipe (full scanwipe shader later)
                ctx.screen.use()
                ctx.viewport = (0, 0, self._width, self._height)
                ctx.clear(0.0, 0.0, 0.0, 1.0)
                self._fbo_a.color_attachments[0].use(location=0)
                self._fbo_b.color_attachments[0].use(location=1)
                self._blend_prog["tex_a"].value = 0
                self._blend_prog["tex_b"].value = 1
                self._blend_prog["t"].value = self._transition_t
                self._blend_vao.render(moderngl.TRIANGLE_STRIP)

    def _on_resize(self, w: int, h: int) -> None:
        self._width = w
        self._height = h
        if self._current_effect:
            self._current_effect.resize(w, h)
        if self._next_effect:
            self._next_effect.resize(w, h)
        # Rebuild FBOs at new size
        self._fbo_a = self._make_fbo()
        self._fbo_b = self._make_fbo()

    # ------------------------------------------------------------------ #
    # Public API (called by hotkey handler)                                #
    # ------------------------------------------------------------------ #

    def toggle_fullscreen(self) -> None:
        self._fullscreen = not self._fullscreen
        flag = sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP if self._fullscreen else 0
        sdl2.SDL_SetWindowFullscreen(self._window, flag)

    def toggle_pause(self) -> None:
        self._paused = not self._paused

    def goto_effect(self, cls: Type[BaseEffect]) -> None:
        self._switch_effect(cls)

    def goto_ansi(self, ansi_dir: str) -> None:
        """Launch ANSIViewer with an explicit art directory."""
        from unicornviz.effects.ansi_viewer import ANSIViewer
        if self._next_effect is not None:
            self._next_effect.destroy()
        cfg_override = {"ansi_dir": ansi_dir}
        self._next_effect = ANSIViewer(self._ctx, self._width, self._height, cfg_override)
        self._transition_t = 0.0

    @property
    def paused(self) -> bool:
        return self._paused
