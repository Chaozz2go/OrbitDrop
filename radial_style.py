"""Shared native radial surfaces and rounded, genuinely clickable segments."""
import math
from PySide6.QtCore import QRectF,QPointF,Qt
from PySide6.QtGui import QPainterPath,QColor,QLinearGradient,QPen


def rounded_sector(center,outer,inner,start,span,corner=12):
    # Angles run clockwise from the top; round the four joins between arcs/radii.
    a=math.radians(start-90);b=math.radians(start+span-90)
    corner=min(corner,(outer-inner)/3,inner*math.radians(span)/5)
    da=corner/outer;db=corner/inner
    def point(radius,angle):return QPointF(center.x()+radius*math.cos(angle),center.y()+radius*math.sin(angle))
    out=QRectF(center.x()-outer,center.y()-outer,2*outer,2*outer)
    inside=QRectF(center.x()-inner,center.y()-inner,2*inner,2*inner)
    path=QPainterPath(point(outer,a+da));path.arcTo(out,-math.degrees(a+da),-math.degrees(b-a-2*da))
    path.quadTo(point(outer,b),point(outer-corner,b));path.lineTo(point(inner+corner,b))
    path.quadTo(point(inner,b),point(inner,b-db));path.arcTo(inside,-math.degrees(b-db),math.degrees(b-a-2*db))
    path.quadTo(point(inner,a),point(inner+corner,a));path.lineTo(point(outer-corner,a));path.quadTo(point(outer,a),point(outer,a+da));path.closeSubpath()
    return path


def surface(p,path,accent,selected=False):
    accent=QColor(accent);gradient=QLinearGradient(path.boundingRect().topLeft(),path.boundingRect().bottomRight())
    gradient.setColorAt(0,accent.darker(125) if selected else QColor('#263548'))
    gradient.setColorAt(1,accent.darker(205) if selected else QColor('#172231'))
    p.save();p.translate(0,3);p.fillPath(path,QColor(0,0,0,55));p.restore()
    p.setBrush(gradient);p.setPen(QPen(accent if selected else QColor('#415267'),1.6 if selected else 1));p.drawPath(path)
