from __future__ import annotations

from ..foundation.tk_app import MBSApp, create_root

DesktopApp = MBSApp


def create_desktop_root():
    return create_root()


def launch_desktop_gui() -> None:
    root = create_root()
    MBSApp(root)
    root.mainloop()
