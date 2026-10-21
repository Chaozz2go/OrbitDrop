"""Shared timeline viewport: filmstrip and waveform always zoom/scroll together."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QScrollArea,QSlider,QLabel
from editor_chrome import action_button

class TimelineView(QWidget):
    def __init__(self,tracks):
        super().__init__();self.tracks=tracks;self.factor=1.
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(4)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.content=QWidget();column=QVBoxLayout(self.content);column.setContentsMargins(0,0,0,0);column.setSpacing(6)
        for track in tracks:column.addWidget(track)
        self.scroll.setWidget(self.content);layout.addWidget(self.scroll,1)
        row=QHBoxLayout();self.controls=row;layout.addLayout(row);self.label=QLabel('Zoom 100 %');row.addWidget(self.label);self.zoom=QSlider(Qt.Orientation.Horizontal);self.zoom.setRange(100,1600);self.zoom.setValue(100);self.zoom.setMaximumWidth(260);row.addWidget(self.zoom)
        fit=action_button('Einpassen');fit.clicked.connect(lambda:self.zoom.setValue(100));row.addWidget(fit);row.addStretch();self.zoom.valueChanged.connect(self.set_zoom)
        height=sum(t.minimumHeight() for t in tracks)+6*(len(tracks)-1);self.scroll.setMinimumHeight(height+24)
    def set_zoom(self,value):
        self.factor=value/100;self.label.setText(f'Zoom {value} %');self.resize_track();QTimer.singleShot(0,self.center_playhead)
    def resize_track(self):self.content.setMinimumWidth(max(100,round(self.scroll.viewport().width()*self.factor)))
    def resizeEvent(self,event):super().resizeEvent(event);self.resize_track()
    def center_playhead(self):
        position=getattr(self.tracks[0],'position',0);width=self.content.width();viewport=self.scroll.viewport().width();self.scroll.horizontalScrollBar().setValue(round(position*width-viewport/2))
    def follow(self):
        x=getattr(self.tracks[0],'position',0)*self.content.width();bar=self.scroll.horizontalScrollBar();width=self.scroll.viewport().width()
        if x<bar.value() or x>bar.value()+width:bar.setValue(round(x-width/4))


def visible_ticks(duration,left,width,clip_left,clip_right):
    """Readable time ticks adapt to zoom; generate only the visible interval."""
    import math
    wanted=duration/max(1,width)*95;power=10**math.floor(math.log10(max(1e-9,wanted)));step=next(value*power for value in (1,2,5,10) if value*power>=wanted)
    first=max(0,math.floor((clip_left-left)/max(1,width)*duration/step));last=min(math.ceil(duration/step),math.ceil((clip_right-left)/max(1,width)*duration/step))
    for tick in range(first,last+1):
        seconds=tick*step
        if seconds>duration+1e-8:continue
        decimals=2 if step<.1 else 1 if step<1 else 0;rest=seconds%60;label=f'{int(seconds//60):02}:'+f'{rest:0{3+decimals if decimals else 2}.{decimals}f}'
        yield seconds,left+width*seconds/duration,label
