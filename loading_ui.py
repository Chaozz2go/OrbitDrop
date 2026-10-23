"""Progress only when measurable; otherwise show the current loading phase."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QProgressBar

class LoadingIndicator(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0);box.setSpacing(4)
        self.label=QLabel();self.label.setWordWrap(True);self.bar=QProgressBar();box.addWidget(self.label);box.addWidget(self.bar);self.hide()
    def busy(self,text):
        self.label.setText(text);self.bar.setRange(0,0);self.bar.show();self.show()
    def progress(self,value,text):
        self.label.setText(text);self.bar.setRange(0,100);self.bar.setValue(max(0,min(100,int(value))));self.bar.show();self.show()
    def finish(self):self.hide()
