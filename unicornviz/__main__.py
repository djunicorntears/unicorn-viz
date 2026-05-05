"""
Entry point for both ``python -m unicornviz`` and the
``unicorn-viz`` console-script installed by pyproject.toml.

SDL2 driver selection (Wayland vs X11) happens in app.py before
``import sdl2`` so the environment variable is set before SDL loads.
"""
from unicornviz.app import App


def main() -> None:
    """Create and run the main application."""
    app = App()
    app.run()


if __name__ == "__main__":
    main()
