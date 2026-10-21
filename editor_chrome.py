"""Consistent editor headings, surfaces and action hierarchy."""
from PySide6.QtWidgets import QLabel
from app_ui import STYLE

EDITOR_STYLE=STYLE+'''
QLabel#editorTitle{font-size:19pt;font-weight:650;color:#f2f7ff;}
QLabel#editorSubtitle{color:#a5b7cd;font-size:9pt;}
QWidget#editorControls{background:#192536;border:1px solid #34475d;border-radius:14px;}
QPushButton{background:#233246;color:#d8e4f1;border:1px solid #40566c;}
QPushButton:hover{background:#304961;border-color:#7197b7;}
QPushButton#primaryAction{background:#83dfc0;color:#102d25;border:1px solid #a3f2d6;}
QPushButton#primaryAction:hover{background:#abf4d9;}
QPushButton#originalPreview:pressed{background:#83dfc0;color:#102d25;}
QScrollArea{background:transparent;border:0;}
'''


def heading(layout,title,subtitle):
    label=QLabel(title);label.setObjectName('editorTitle');layout.addWidget(label)
    hint=QLabel(subtitle);hint.setObjectName('editorSubtitle');hint.setWordWrap(True);layout.addWidget(hint)
