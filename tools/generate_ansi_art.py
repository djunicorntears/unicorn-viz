#!/usr/bin/env python3
"""
Generate classic-style .ANS files for the Unicorn Viz asset library.
Produces authentic CP437 + ANSI escape sequences + SAUCE records.
Run from the project root: .venv/bin/python tools/generate_ansi_art.py
"""
from __future__ import annotations
import struct
import math
import random
import os


# ── ANSI helpers ─────────────────────────────────────────────────────────────

ESC = b"\x1b"

def fg(c: int) -> bytes:
    """Set foreground colour (0-15, standard CGA)."""
    if c < 8:
        return ESC + f"[{30+c}m".encode()
    else:
        return ESC + f"[{22+c}m".encode()   # 90-97 bright via high-intensity

def bg(c: int) -> bytes:
    """Set background colour (0-7)."""
    return ESC + f"[{40 + (c & 7)}m".encode()

def attr(*codes: int) -> bytes:
    return ESC + ("[" + ";".join(str(c) for c in codes) + "m").encode()

RESET = attr(0)

def move(row: int, col: int) -> bytes:
    return ESC + f"[{row};{col}H".encode()

def cls() -> bytes:
    return ESC + b"[2J"

# CP437 block characters
FULL  = b"\xdb"   # █
UPPER = b"\xdf"   # ▀
LOWER = b"\xdc"   # ▄
LEFT  = b"\xdd"   # ▌
RIGHT = b"\xde"   # ▐
SHADE1 = b"\xb0"  # ░
SHADE2 = b"\xb1"  # ▒
SHADE3 = b"\xb2"  # ▓
BOX_H  = b"\xc4"  # ─
BOX_V  = b"\xb3"  # │
BOX_TL = b"\xda"  # ┌
BOX_TR = b"\xbf"  # ┐
BOX_BL = b"\xc0"  # └
BOX_BR = b"\xd9"  # ┘
BOX_LT = b"\xc3"  # ├
BOX_RT = b"\xb4"  # ┤
BOX_TB = b"\xc2"  # ┬
BOX_BB = b"\xc1"  # ┴
DBL_H  = b"\xcd"  # ═
DBL_V  = b"\xba"  # ║
DBL_TL = b"\xc9"  # ╔
DBL_TR = b"\xbb"  # ╗
DBL_BL = b"\xc8"  # ╚
DBL_BR = b"\xbc"  # ╝


def sauce(title: str, author: str, group: str, width: int = 80, height: int = 25) -> bytes:
    """Build a SAUCE record (standard ANSI art metadata footer)."""
    def pad(s: str, n: int) -> bytes:
        return s.encode("ascii", errors="replace")[:n].ljust(n)

    record = b"SAUCE"                          # ID
    record += b"00"                            # version
    record += pad(title, 35)
    record += pad(author, 20)
    record += pad(group, 20)
    record += b"20260505"                      # date YYYYMMDD
    record += struct.pack("<I", 0)             # filesize placeholder
    record += bytes([1])                       # datatype: character
    record += bytes([1])                       # filetype: ANSI
    record += struct.pack("<H", width)
    record += struct.pack("<H", height)
    record += struct.pack("<H", 0)             # TInfo3
    record += struct.pack("<H", 0)             # TInfo4
    record += bytes([0])                       # number of COMNT blocks
    record += bytes([1])                       # TFlags: bit0 = iCE colors
    record += b"\x00" * 22                     # TInfoS
    return b"\x1a" + record                    # SUB (1) + SAUCE (128) = 129 bytes


# ── Art generator functions ───────────────────────────────────────────────────

def make_unicorn_viz_title() -> bytes:
    """Big block-letter title screen for Unicorn Viz."""
    buf = bytearray()

    W, H = 80, 25

    # Background — dark blue
    buf += attr(0, 44)
    buf += b" " * (W * H)
    buf += move(1, 1)

    # Gradient background rows
    grad_cols = [0, 1, 1, 9, 9, 1, 1, 0]  # dark to bright blue
    for row in range(H):
        c = grad_cols[min(row * len(grad_cols) // H, len(grad_cols)-1)]
        buf += move(row + 1, 1)
        buf += attr(0)
        buf += bg(c & 7)
        buf += b" " * W

    # Double-box border
    buf += move(1, 1)
    buf += attr(1, 33, 40)   # bright yellow on black
    buf += DBL_TL + DBL_H * 78 + DBL_TR
    for r in range(2, 25):
        buf += move(r, 1)
        buf += DBL_V
        buf += move(r, 80)
        buf += DBL_V
    buf += move(25, 1)
    buf += DBL_BL + DBL_H * 78 + DBL_BR

    # ═══ UNICORN VIZ ═══ banner using block chars
    TITLE = " UNICORN VIZ "
    title_art_lines = [
        " ▄  ▄ ▄ ▄ ▄ ▄ ▄▄  ▄▄  ▄ ▄ ",
        " █  █ █ █ █ █ █ █ █ █ ████ ",
        " ▀█▄█ ▀█▀ █ █ █▄▀ █ █ █  █ ",
        "  ▀▀  ▀   ▀▀▀ ▀   ▀▀▀ ▀  ▀ ",
    ]

    # Colour-cycle title text
    title_text = "  *** UNICORN VIZ ***  "
    colours = [9, 13, 11, 10, 14, 9, 13, 11]
    buf += move(4, 30)
    buf += attr(1, 40)
    for i, ch in enumerate(title_text):
        c = colours[i % len(colours)]
        buf += fg(c)
        buf += ch.encode("cp437", errors="replace")

    # Subtitle
    buf += move(6, 22)
    buf += attr(0, 36, 40)
    buf += b"Modern Demoscene Visualizer  v0.1"

    # Group credits  
    credits = [
        (8,  14, 3,  "Greetings to:"),
        (9,  16, 9,  "Razor 1911   Future Crew   ACiD Productions"),
        (10, 16, 11, "The Silents  Triton        Fairlight"),
        (11, 16, 13, "Cascadia     Desire        Loonies"),
        (13, 14, 7,  "─────────────────────────────────────────────"),
        (14, 20, 10, "♦  Keep the scene alive!  ♦"),
        (16, 14, 7,  "─────────────────────────────────────────────"),
    ]
    for row, col, colour, text in credits:
        buf += move(row, col)
        buf += attr(1 if colour > 7 else 0, 40)
        buf += fg(colour & 7 if colour < 8 else colour)
        buf += text.encode("cp437", errors="replace")

    # Hotkey bar at bottom
    buf += move(22, 3)
    buf += attr(0, 42, 30)
    buf += b" N/P:Next/Prev "
    buf += attr(0, 44, 37)
    buf += b" F:Fullscreen "
    buf += attr(0, 46, 30)
    buf += b" SPC:Pause "
    buf += attr(0, 43, 30)
    buf += b" ESC:Quit "
    buf += attr(0, 47, 30)
    buf += b" H:Help "

    # Plasma-style colour bar
    for col in range(2, 79):
        hue = int(col * 6 / 77)
        colours_bar = [1, 9, 3, 11, 2, 10]
        buf += move(23, col)
        buf += attr(1, 40)
        buf += fg(colours_bar[hue % len(colours_bar)])
        buf += SHADE3

    buf += RESET

    return bytes(buf) + sauce("UNICORN VIZ - Title", "unicorn-viz", "unicorn-viz", 80, 25)


def make_fire_scene() -> bytes:
    """An ANSI art campfire scene."""
    buf = bytearray()
    W, H = 80, 25

    # Black background
    buf += attr(0, 40)
    for r in range(1, H + 1):
        buf += move(r, 1)
        buf += b" " * W

    # Stars in upper half
    buf += attr(1, 40)
    random.seed(0x1911)
    star_chars = [b".", b"+", b"*", b"\xf9", b"\xfa"]
    star_cols = [7, 15, 15, 14, 11]
    for _ in range(60):
        sr = random.randint(1, 9)
        sc = random.randint(2, 79)
        ci = random.randrange(len(star_chars))
        buf += move(sr, sc)
        buf += fg(star_cols[ci])
        buf += star_chars[ci]

    # Ground
    for col in range(1, 81):
        buf += move(18, col)
        buf += attr(0, 42, 30)
        buf += FULL if col % 3 else SHADE3

    # Fire — layers
    fire_layers = [
        # (row, col_start, colour_fg, colour_bg, chars)
        (17, 36, 12, 0,  b"\xdb\xdb\xdb\xdb\xdb"),
        (16, 35, 4,  0,  b"\xdb\xdb\xdc\xdb\xdb\xdb"),
        (15, 34, 12, 0,  b"  \xdb\xdb\xdb  "),
        (14, 35, 4,  0,  b" \xdc\xdb\xdb\xdc "),
        (13, 36, 12, 0,  b"\xdc\xdb\xdc"),
        (12, 37, 14, 0,  b"\xdc\xdb"),
        (11, 37, 14, 0,  b"\xdf "),
    ]
    for row, col, cfore, cback, chars in fire_layers:
        buf += move(row, col)
        buf += attr(1 if cfore > 7 else 0, 40 + cback)
        buf += fg(cfore & 7)
        buf += chars

    # Smoke
    smoke = [(10, 38, 8), (9, 39, 8), (8, 38, 7), (7, 39, 7)]
    for row, col, c in smoke:
        buf += move(row, col)
        buf += attr(0, 40)
        buf += fg(c)
        buf += SHADE1

    # Log base
    buf += move(18, 34)
    buf += attr(0, 40)
    buf += fg(3)
    buf += b"\\\\====///"

    # Title strip
    buf += move(20, 24)
    buf += attr(1, 40)
    buf += fg(12)
    buf += b" * * *  F I R E  * * * "

    buf += RESET
    return bytes(buf) + sauce("Fire Scene", "unicorn-viz", "unicorn-viz", 80, 25)


def make_gradient_palette() -> bytes:
    """Classic gradient/palette test — every colour combination."""
    buf = bytearray()
    W = 80

    title = " ANSI COLOUR & BLOCK CHAR TEST "
    buf += move(1, (W - len(title)) // 2 + 1)
    buf += attr(1, 40)
    buf += fg(11)
    buf += title.encode()

    # Foreground colours on all backgrounds
    buf += move(3, 2)
    buf += attr(0, 40)
    buf += fg(7)
    buf += b"FG\\BG   "
    for bg_c in range(8):
        label = f"  {bg_c}   "
        buf += attr(0, 40 + bg_c)
        buf += fg(7 if bg_c < 3 else 0)
        buf += label.encode()

    buf += move(4, 2)
    buf += attr(0)
    buf += fg(8)
    buf += b"       " + BOX_H * 70

    for fg_c in range(16):
        buf += move(5 + fg_c, 2)
        buf += attr(0, 40)
        buf += fg(7)
        label = f"  {fg_c:>2}   "
        buf += label.encode()
        for bg_c in range(8):
            buf += attr(1 if fg_c > 7 else 0, 40 + bg_c)
            buf += fg(fg_c & 7)
            buf += b" " + FULL + FULL + FULL + b" "

    # Block char showcase
    row = 23
    blocks = [SHADE1, SHADE2, SHADE3, FULL, UPPER, LOWER, LEFT, RIGHT]
    block_labels = ["░", "▒", "▓", "█", "▀", "▄", "▌", "▐"]
    buf += move(row, 2)
    buf += attr(1, 40)
    for i, (blk, label) in enumerate(zip(blocks, block_labels)):
        buf += fg((i + 9) & 15)
        buf += blk * 4

    buf += move(row + 1, 2)
    buf += attr(0, 40, 37)
    buf += b"Block: " + b"".join(b*4 for b in blocks)

    buf += RESET
    return bytes(buf) + sauce("Colour Test", "unicorn-viz", "unicorn-viz", 80, 25)


def make_razor_bbs() -> bytes:
    """Faux Razor 1911 BBS login screen style."""
    buf = bytearray()
    W, H = 80, 25

    # Black background
    buf += attr(0, 40)
    for r in range(1, H + 1):
        buf += move(r, 1)
        buf += b" " * W

    # Top border with angled blocks
    buf += move(1, 1)
    buf += attr(1, 44, 37)
    buf += b"\xc9" + b"\xcd" * 78 + b"\xbb"

    # Side bars
    for r in range(2, 25):
        buf += move(r, 1);  buf += attr(1, 44, 37); buf += b"\xba"
        buf += move(r, 80); buf += attr(1, 44, 37); buf += b"\xba"

    buf += move(25, 1)
    buf += attr(1, 44, 37)
    buf += b"\xc8" + b"\xcd" * 78 + b"\xbc"

    # RAZOR heading
    razor_lines = [
        "   ██████╗  █████╗ ███████╗ ██████╗ ██████╗ ",
        "   ██╔══██╗██╔══██╗╚══███╔╝██╔═══██╗██╔══██╗",
        "   ██████╔╝███████║  ███╔╝ ██║   ██║██████╔╝",
        "   ██╔══██╗██╔══██║ ███╔╝  ██║   ██║██╔══██╗",
        "   ██║  ██║██║  ██║███████╗╚██████╔╝██║  ██║",
        "   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝",
    ]
    colours_razor = [9, 9, 12, 12, 4, 4]
    for i, line in enumerate(razor_lines):
        buf += move(3 + i, 3)
        buf += attr(1 if colours_razor[i] > 7 else 0, 40)
        buf += fg(colours_razor[i] & 7)
        buf += line.encode("cp437", errors="replace")

    buf += move(10, 20)
    buf += attr(1, 40, 36)
    buf += b" 1 9 1 1 "

    buf += move(11, 15)
    buf += attr(0, 40, 37)
    buf += b"\xc4" * 50

    # BBS login box
    buf += move(13, 12)
    buf += attr(1, 40, 33)
    buf += b"\xda" + b"\xc4" * 54 + b"\xbf"
    buf += move(14, 12)
    buf += attr(1, 40, 33)
    buf += b"\xb3"
    buf += attr(0, 40, 37)
    buf += b"  Handle: ___________________________           "
    buf += attr(1, 40, 33)
    buf += b"\xb3"
    buf += move(15, 12)
    buf += attr(1, 40, 33)
    buf += b"\xb3"
    buf += attr(0, 40, 37)
    buf += b"  Passwd: ___________________________           "
    buf += attr(1, 40, 33)
    buf += b"\xb3"
    buf += move(16, 12)
    buf += attr(1, 40, 33)
    buf += b"\xc0" + b"\xc4" * 54 + b"\xd9"

    buf += move(18, 16)
    buf += attr(0, 40, 36)
    buf += b"\xb0 "
    buf += attr(1, 40, 33)
    buf += b"[ENTER] to continue   [Q] to quit "
    buf += attr(0, 40, 36)
    buf += b"\xb0"

    # Footer
    buf += move(22, 10)
    buf += attr(0, 40, 32)
    buf += b"   Proudly Serving the Warez Community Since 1991   "
    buf += move(23, 15)
    buf += attr(1, 40, 15)
    buf += b" Node 1/16  SysOp: Sector9  28800 bps "

    buf += RESET
    return bytes(buf) + sauce("Razor 1911 BBS", "unicorn-viz", "Razor 1911", 80, 25)


def make_acid_logo() -> bytes:
    """ACiD Productions-style logo/info screen."""
    buf = bytearray()
    W, H = 80, 25

    buf += attr(0, 40)
    for r in range(1, H+1):
        buf += move(r, 1)
        buf += b" " * W

    # Scanline-style bg
    for r in range(1, H+1, 2):
        buf += move(r, 1)
        buf += attr(0, 44)
        buf += b" " * W

    # ACiD logo built with block chars
    acid_rows = [
        (3,  4, 11, b"  \xdb\xdb\xdb\xdb     \xdb\xdb\xdb\xdb   \xdb\xdb\xdb\xdb\xdb  \xdb\xdb   \xdb\xdb  "),
        (4,  4, 3,  b" \xdb\xdb  \xdb\xdb   \xdb\xdb  \xdb\xdb  \xdb\xdb       \xdb\xdb\xdb \xdb\xdb  "),
        (5,  4, 11, b" \xdb\xdb\xdb\xdb\xdb\xdb   \xdb\xdb        \xdb\xdb\xdb\xdb\xdb   \xdb\xdb\xdb\xdb\xdb\xdb  "),
        (6,  4, 3,  b" \xdb\xdb  \xdb\xdb   \xdb\xdb  \xdb\xdb  \xdb\xdb       \xdb\xdb \xdb\xdb\xdb  "),
        (7,  4, 11, b" \xdb\xdb  \xdb\xdb    \xdb\xdb\xdb\xdb    \xdb\xdb\xdb\xdb\xdb  \xdb\xdb  \xdb\xdb  "),
    ]
    for row, col, colour, chars in acid_rows:
        buf += move(row, col)
        buf += attr(1 if colour > 7 else 0, 40)
        buf += fg(colour & 7)
        buf += chars

    buf += move(3, 44)
    buf += attr(1, 40, 13)
    buf += b"PRODUCTIONS"

    buf += move(5, 44)
    buf += attr(0, 40, 7)
    buf += b"Est. 1990"

    buf += move(7, 44)
    buf += attr(1, 40, 14)
    buf += b"The Art of Tomorrow"

    # Divider
    buf += move(9, 3)
    buf += attr(1, 40, 11)
    buf += b"\xcd" * 74

    # Pack info
    info = [
        (10, 5, 14, "ACiD0693 - June 1993 Artpack"),
        (11, 5,  7, "Artists: RaD Man  z!r0  Lord Jazz  Blockatiel"),
        (12, 5,  7, "Groups:  ACiD      iCE      Aces of ANSI Art"),
        (14, 5, 11, "ANSI  ─  RIP  ─  BIN  ─  ASCII  ─  MOD music"),
        (16, 5, 13, "For best results view at 80×25 in 16 colours."),
        (17, 5,  8, "Use a proper ANSI viewer or BBS terminal."),
    ]
    for row, col, colour, text in info:
        buf += move(row, col)
        buf += attr(1 if colour > 7 else 0, 40)
        buf += fg(colour & 7)
        buf += text.encode("cp437", errors="replace")

    # Footer bar
    buf += move(23, 1)
    buf += attr(0, 41, 33)
    buf += b"  ACiD  "
    buf += attr(0, 44, 37)
    buf += b"  artscene.textfiles.com  "
    buf += attr(0, 41, 33)
    buf += b"  16colo.rs  "
    buf += attr(0, 40, 36)
    buf += b" THE ARTSCENE LIVES ON "

    buf += RESET
    return bytes(buf) + sauce("ACiD Productions Info", "unicorn-viz", "ACiD", 80, 25)


def make_plasma_test() -> bytes:
    """Plasma gradient via palette cycling of block chars."""
    buf = bytearray()
    W, H = 80, 25

    # Palette: colour-cycle through 16 colours row+col
    for r in range(1, H+1):
        for c in range(1, W+1):
            cv = int((math.sin(r * 0.4 + c * 0.15) + math.cos(r * 0.25 - c * 0.3)) * 4 + 8)
            cv = max(0, min(15, cv))
            buf += move(r, c)
            shade_idx = (r + c) % 4
            shade = [SHADE1, SHADE2, SHADE3, FULL][shade_idx]
            bg_c = cv % 8
            fg_c = (cv + 8) % 16
            buf += attr(1 if fg_c > 7 else 0, 40 + bg_c)
            buf += fg(fg_c & 7)
            buf += shade

    # Label
    buf += move(13, 28)
    buf += attr(1, 40, 15)
    buf += b" *** PLASMA *** "

    buf += RESET
    return bytes(buf) + sauce("Plasma Test", "unicorn-viz", "unicorn-viz", 80, 25)


def make_future_crew() -> bytes:
    """Future Crew tribute / Second Reality homage."""
    buf = bytearray()
    W, H = 80, 25

    buf += attr(0, 40)
    for r in range(1, H+1):
        buf += move(r, 1)
        buf += b" " * W

    # Top header strip
    buf += move(1, 1)
    buf += attr(1, 40, 9)
    buf += b"\xdb" * W
    buf += move(2, 1)
    buf += attr(0, 44, 37)
    buf += b" " * W

    buf += move(2, 20)
    buf += attr(1, 44, 15)
    buf += "FUTURE CREW \x14 SECOND REALITY 1993".encode("cp437")

    buf += move(3, 1)
    buf += attr(1, 40, 9)
    buf += b"\xdb" * W

    # "Second Reality" in big letters using blocks
    sr_art = [
        "  \xdc\xdc\xdc\xdc\xdb   \xdc\xdc\xdc\xdb  \xdc\xdc\xdc\xdb  \xdc\xdc\xdb  \xdc\xdb  \xdc\xdc\xdb  \xdc\xdb",
        "  \xdb    \xdb   \xdb  \xdb\xdb  \xdb  \xdb\xdb  \xdb\xdb\xdb  \xdb\xdb\xdb  \xdb\xdb\xdb",
        "  \xdc\xdc\xdc\xdb   \xdb\xdb\xdb\xdb\xdb\xdb  \xdb\xdb\xdb\xdb\xdb  \xdb\xdb\xdb\xdb  \xdb\xdb\xdb\xdb  \xdb",
        "      \xdb   \xdb  \xdb\xdb  \xdb  \xdb\xdb  \xdb\xdb  \xdb  \xdb\xdb  \xdb",
        "  \xdc\xdc\xdc\xdb   \xdb  \xdb \xdc\xdc\xdc\xdb  \xdc\xdc\xdc\xdb  \xdb  \xdc\xdc\xdb  \xdb",
    ]
    colours_fc = [9, 11, 13, 11, 9]
    for i, line in enumerate(sr_art):
        buf += move(5 + i, 4)
        buf += attr(1, 40)
        buf += fg(colours_fc[i] & 7)
        buf += line.encode("cp437", errors="replace")

    buf += move(11, 10)
    buf += attr(0, 40, 36)
    buf += b"\xcd" * 60

    # Credits
    credits_fc = [
        (12, 10, 11, "Skaven        ─  Music, Code"),
        (13, 10, 13, "Psi           ─  Code (3D engine, FX)"),
        (14, 10, 11, "Marvel        ─  Code (intro, setup)"),
        (15, 10, 13, "Gore          ─  Graphics"),
        (16, 10, 11, "Abyss         ─  Graphics, Design"),
        (17, 10, 15, "Purple Motion ─  Music"),
    ]
    for row, col, colour, text in credits_fc:
        buf += move(row, col)
        buf += attr(1 if colour > 7 else 0, 40)
        buf += fg(colour & 7)
        buf += text.encode("cp437", errors="replace")

    buf += move(19, 10)
    buf += attr(0, 40, 36)
    buf += b"\xcd" * 60

    # Classic PC speaker beep text
    buf += move(20, 15)
    buf += attr(1, 40, 14)
    buf += "Assembly '93 - Voted #1 Demo of All Time".encode("cp437")

    buf += move(22, 18)
    buf += attr(0, 40, 8)
    buf += b"\"If it's not Future Crew, it's not worth watching.\""

    # Bottom bar
    buf += move(25, 1)
    buf += attr(1, 40, 9)
    buf += b"\xdb" * W

    buf += RESET
    return bytes(buf) + sauce("Future Crew Tribute", "unicorn-viz", "Future Crew", 80, 25)


# ── Write all files ───────────────────────────────────────────────────────────

def main() -> None:
    out_dir = "assets/ansi"
    os.makedirs(out_dir, exist_ok=True)

    files = {
        "unicorn_viz_title.ans": make_unicorn_viz_title,
        "fire_scene.ans":        make_fire_scene,
        "colour_test.ans":       make_gradient_palette,
        "razor_bbs.ans":         make_razor_bbs,
        "acid_logo.ans":         make_acid_logo,
        "plasma_test.ans":       make_plasma_test,
        "future_crew.ans":       make_future_crew,
    }

    for fname, fn in files.items():
        path = os.path.join(out_dir, fname)
        data = fn()
        with open(path, "wb") as f:
            f.write(data)
        print(f"  wrote {path}  ({len(data)} bytes)")

    print(f"\nGenerated {len(files)} .ANS files in {out_dir}/")


if __name__ == "__main__":
    main()
