from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QHBoxLayout,QSlider

class SliderField(QWidget):
    """A precise numeric editor paired with an immediately draggable slider."""
    def __init__(self,editor,decimals=0,parent=None):
        super().__init__(parent);self.editor=editor;self.scale=10**decimals
        layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(14)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.setRange(round(editor.minimum()*self.scale),round(editor.maximum()*self.scale));self.slider.setValue(round(editor.value()*self.scale));self.slider.setMinimumWidth(180);layout.addWidget(self.slider,1)
        editor.setFixedWidth(98);layout.addWidget(editor)
        self.slider.valueChanged.connect(lambda value:editor.setValue(value/self.scale if decimals else value))
        editor.valueChanged.connect(lambda value:self.slider.setValue(round(value*self.scale)))
        editor.enabledChanged.connect(self.update_enabled) if hasattr(editor,'enabledChanged') else None
    def update_enabled(self,*args):self.slider.setEnabled(self.editor.isEnabled())
