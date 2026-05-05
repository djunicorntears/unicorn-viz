"""Entry point for `python -m unicornviz` and the `unicorn-viz` script."""
from unicornviz.app import App


def main() -> None:
    app = App()
    app.run()


if __name__ == "__main__":
    main()
