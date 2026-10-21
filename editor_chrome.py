"""Shared editor chrome; every window uses the same theme."""
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt
from ui_theme import STYLE,toolbar,action_button,ensure_gui_lifetimes

EDITOR_STYLE=STYLE

def heading(layout,title,subtitle):
    ensure_gui_lifetimes()
    layout.setContentsMargins(18,16,18,16);layout.setSpacing(10)
    label=QLabel(title);label.setObjectName('editorTitle');layout.addWidget(label)
    hint=QLabel(subtitle);hint.setTextFormat(Qt.TextFormat.PlainText);hint.setObjectName('editorSubtitle');hint.setWordWrap(True);layout.addWidget(hint)
