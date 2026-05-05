#!/usr/bin/env bash
# Unicorn Viz launcher
# Auto-detects Wayland vs X11 and launches in the project venv.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV="$SCRIPT_DIR/.venv"
if [[ ! -d "$VENV" ]]; then
    echo "No venv found. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

# Wayland-first; fall back to X11
if [[ -n "$WAYLAND_DISPLAY" ]]; then
    export SDL_VIDEODRIVER=wayland
elif [[ -n "$DISPLAY" ]]; then
    export SDL_VIDEODRIVER=x11
fi

exec "$VENV/bin/python" -m unicornviz "$@"
