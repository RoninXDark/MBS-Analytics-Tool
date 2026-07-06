"""Compatibility shim for removed Streamlit dashboard.

The project is desktop GUI only.
Use `python main.py desktop-gui` (or `run_desktop_gui.bat`) instead.
"""

from __future__ import annotations


def main() -> None:
    raise SystemExit(
        "Streamlit dashboard has been removed. "
        "Launch the desktop interface with `python main.py desktop-gui`."
    )


if __name__ == "__main__":
    main()
