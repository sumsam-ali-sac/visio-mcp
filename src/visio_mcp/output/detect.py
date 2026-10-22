"""Detect whether Microsoft Visio desktop is installed for automation."""

from __future__ import annotations

import sys


def visio_available() -> bool:
    """True on Windows when Visio desktop is registered for automation."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Visio.Application\CLSID"))
        return True
    except OSError:
        return False
