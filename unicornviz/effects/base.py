"""BaseEffect — abstract base class all effects inherit from."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import moderngl


class AudioData:
    """Snapshot of audio state passed to effects each frame."""

    __slots__ = ("fft", "waveform", "bass", "mid", "treble", "beat", "bpm")

    def __init__(self) -> None:
        self.fft: np.ndarray = np.zeros(512, dtype=np.float32)
        self.waveform: np.ndarray = np.zeros(512, dtype=np.float32)
        self.bass: float = 0.0
        self.mid: float = 0.0
        self.treble: float = 0.0
        self.beat: float = 0.0
        self.bpm: float = 120.0


class BaseEffect(ABC):
    """
    All effects subclass this.

    Lifecycle:
        __init__(ctx, width, height, config)  — called once at startup
        resize(width, height)                 — called on window resize
        update(dt, audio)                     — called every frame before render
        render()                              — draw to currently bound FBO
        destroy()                             — release GL resources

    Metadata class attributes:
        NAME    — display name shown in overlay
        AUTHOR  — optional author credit
        TAGS    — list of strings: 'classic', 'audio', 'ansi', 'futuristic', etc.
    """

    NAME: str = "Effect"
    AUTHOR: str = ""
    TAGS: list[str] = []

    def __init__(
        self,
        ctx: "moderngl.Context",
        width: int,
        height: int,
        config: dict,
    ) -> None:
        self.ctx = ctx
        self.width = width
        self.height = height
        self.config = config
        self.time: float = 0.0
        # Per-effect tweakable parameters (exposed to MIDI mapping)
        self.parameters: dict[str, float] = {}
        self._init()

    # ------------------------------------------------------------------ #
    # Subclass interface                                                   #
    # ------------------------------------------------------------------ #

    def _init(self) -> None:
        """Override to set up GL resources instead of overriding __init__."""

    @abstractmethod
    def render(self) -> None:
        """Draw the effect to the currently bound FBO."""

    def update(self, dt: float, audio: AudioData) -> None:
        """Advance internal state. Default: tick self.time."""
        self.time += dt

    def resize(self, width: int, height: int) -> None:
        """Handle window resize."""
        self.width = width
        self.height = height

    def destroy(self) -> None:
        """Release any moderngl resources. Override if needed."""

    def on_midi(self, event: "MidiEvent") -> None:  # noqa: F821
        """
        Handle a MIDI event.  Default: map CC numbers to self.parameters
        using the cc_to_param lookup from MidiManager.
        Effects may override to handle additional mappings.
        """
        if event.type == "cc":
            # Try to find a matching parameter by name from the app-injected map
            param_name = getattr(self, "_midi_cc_map", {}).get(event.number)
            if param_name and param_name in self.parameters:
                lo, hi = 0.0, 4.0
                self.parameters[param_name] = lo + event.value * (hi - lo)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _fullscreen_quad(self) -> tuple["moderngl.VertexArray", "moderngl.Buffer"]:
        """Return a VAO covering [-1,1]² for fullscreen quad rendering."""
        vertices = np.array(
            [-1, -1, -1, 1, 1, -1, 1, 1],
            dtype=np.float32,
        )
        vbo = self.ctx.buffer(vertices)
        vao = self.ctx.simple_vertex_array(
            self._prog, vbo, "in_vert"  # type: ignore[attr-defined]
        )
        return vao, vbo

    def _make_program(self, vert_src: str, frag_src: str) -> "moderngl.Program":
        return self.ctx.program(vertex_shader=vert_src, fragment_shader=frag_src)
