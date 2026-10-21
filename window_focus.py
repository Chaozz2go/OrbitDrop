"""Bring requested windows back from a minimized or covered state."""
from PySide6.QtCore import Qt

def present(window):
    if window.windowState() & Qt.WindowState.WindowMinimized:
        window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized)
    window.show();window.raise_();window.activateWindow()
