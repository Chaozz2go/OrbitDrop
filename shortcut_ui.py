from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox,QHBoxLayout,QLineEdit,QWidget
from shortcuts import KEY_CODES,MODIFIERS,normalize_shortcut

class ShortcutChoice(QComboBox):
    """Editable chord names and optional capture, including modifier-only keys."""
    def __init__(self,value):
        super().__init__();self.setEditable(True);self.addItems(['Shift','Strg','Alt',*[f'F{i}' for i in range(1,25)],*'ABCDEFGHIJKLMNOPQRSTUVWXYZ']);self.setCurrentText(value);self.lineEdit().setPlaceholderText('z. B. F8 oder Strg+E')
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.hidePopup();event.ignore();return
        super().keyPressEvent(event)

class ShortcutCapture(QLineEdit):
    def __init__(self,target):
        super().__init__();self.target=target;self.setReadOnly(True);self.setPlaceholderText('Hier klicken und gewünschte Tasten drücken');self.pending=None
        self.names={getattr(Qt.Key,'Key_'+chr(code)):chr(code) for code in range(65,91)}
        self.names.update({getattr(Qt.Key,'Key_'+str(i)):str(i) for i in range(10)})
        self.names.update({getattr(Qt.Key,'Key_F'+str(i)):'F'+str(i) for i in range(1,25)})
        self.names.update({Qt.Key.Key_Space:'Leertaste',Qt.Key.Key_Tab:'Tab',Qt.Key.Key_CapsLock:'Feststelltaste',Qt.Key.Key_Pause:'Pause',Qt.Key.Key_ScrollLock:'Rollen',Qt.Key.Key_Insert:'Einfügen',Qt.Key.Key_Home:'Pos1',Qt.Key.Key_End:'Ende',Qt.Key.Key_PageUp:'Bild auf',Qt.Key.Key_PageDown:'Bild ab',Qt.Key.Key_Left:'Links',Qt.Key.Key_Right:'Rechts',Qt.Key.Key_Up:'Oben',Qt.Key.Key_Down:'Unten',Qt.Key.Key_Backspace:'Zurücktaste',Qt.Key.Key_Return:'Enter',Qt.Key.Key_Enter:'Enter'})
    def keyPressEvent(self,event):
        if event.isAutoRepeat():return
        if event.key()==Qt.Key.Key_Escape:self.clearFocus();return
        if event.modifiers() & (Qt.KeyboardModifier.MetaModifier|Qt.KeyboardModifier.GroupSwitchModifier):self.setText('Win- und AltGr-Kombinationen sind nicht belegbar.');self.pending=None;return
        mods=[name for name,flag in [('Strg',Qt.KeyboardModifier.ControlModifier),('Alt',Qt.KeyboardModifier.AltModifier),('Shift',Qt.KeyboardModifier.ShiftModifier)] if event.modifiers()&flag]
        lone={Qt.Key.Key_Control:'Strg',Qt.Key.Key_Alt:'Alt',Qt.Key.Key_Shift:'Shift'}
        if event.key() in lone:
            if lone[event.key()] not in mods:mods.append(lone[event.key()])
            self.pending='+'.join(mods)
        elif event.key() in self.names:self.pending='+'.join(mods+[self.names[event.key()]])
        else:self.setText('Diese Taste ist nicht belegbar.');self.pending=None;return
        self.setText(self.pending)
    def keyReleaseEvent(self,event):
        if self.pending:
            try:
                value=normalize_shortcut(self.pending);self.target.setCurrentText(value);self.setText(value)
            except ValueError as error:self.setText(str(error))
            self.pending=None
    def focusNextPrevChild(self,next):return False if self.hasFocus() else super().focusNextPrevChild(next)


def shortcut_row(value):
    choice=ShortcutChoice(value);capture=ShortcutCapture(choice);row=QHBoxLayout();row.addWidget(choice,1);row.addWidget(capture,2)
    return choice,row
