"""Category icons shared with the native octagon renderer."""
from PySide6.QtCore import Qt,QRectF,QPointF

def icon(p,kind,x,y,size=34):
    p.save();p.translate(x-size/2,y-size/2);p.scale(size/40,size/40);p.setBrush(Qt.BrushStyle.NoBrush)
    if kind in ('KONVERTIEREN','AUDIO LADEN','SVG SCHNELL'):
        p.drawLine(5,12,34,12);p.drawLine(25,4,34,12);p.drawLine(25,20,34,12)
        p.drawLine(35,28,6,28);p.drawLine(15,20,6,28);p.drawLine(15,36,6,28)
    elif kind in ('BEARBEITEN','SVG ERWEITERT'):
        for yy,xx in [(9,14),(20,28),(31,10)]:p.drawLine(3,yy,37,yy);p.drawEllipse(QPointF(xx,yy),3.5,3.5)
    else:
        p.drawRoundedRect(QRectF(3,12,34,23),3,3);p.drawRoundedRect(QRectF(13,5,14,8),2,2);p.drawLine(4,22,36,22);p.drawLine(20,18,20,27)
    p.restore()


def paint_wheel(w):
    from octagon_menu import paint
    paint(w)
