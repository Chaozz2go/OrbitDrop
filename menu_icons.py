"""Small vector icons drawn with Qt; no font glyph or image dependencies."""
from PySide6.QtCore import QRectF,QPointF,Qt
from PySide6.QtGui import QPainterPath


def draw_icon(p,label,x,y,size=24):
    p.save();p.translate(x-size/2,y-size/2);p.scale(size/24,size/24);p.setBrush(Qt.BrushStyle.NoBrush)
    def line(x1,y1,x2,y2):p.drawLine(QPointF(x1,y1),QPointF(x2,y2))
    def rect(x,y,w,h,r=2):p.drawRoundedRect(QRectF(x,y,w,h),r,r)
    if label=='KOMPRIMIEREN':
        line(2,2,9,9);line(9,9,3,9);line(9,9,9,3);line(22,22,15,15);line(15,15,15,21);line(15,15,21,15)
    elif label=='MARKIEREN':
        rect(2,12,12,9);line(10,15,19,3);line(19,3,22,6);line(22,6,13,18)
    elif label.startswith('quick:') or label=='SCHNELLAKTIONEN':
        path=QPainterPath(QPointF(14,2));path.lineTo(5,13);path.lineTo(11,13);path.lineTo(9,22);path.lineTo(20,10);path.lineTo(13,10);path.closeSubpath();p.drawPath(path)
    elif label=='ZURÜCK':
        line(20,12,4,12);line(4,12,10,6);line(4,12,10,18)
    elif label in ('BILD EDITOR','EINSTELLUNGEN'):
        for yy,xx in [(5,8),(12,16),(19,7)]:line(3,yy,21,yy);p.drawEllipse(QPointF(xx,yy),2.5,2.5)
    elif label=='ZUSCHNEIDEN':
        line(7,2,7,17);line(7,17,22,17);line(2,7,17,7);line(17,7,17,22)
    elif label.startswith('90°') or label=='180°':
        p.drawArc(QRectF(5,5,15,15),-40*16,270*16);line(5,5,5,11);line(5,5,11,5)
    elif label in ('SCHWARZWEISS','BITMAP'):
        p.drawEllipse(QRectF(3,3,18,18));line(12,3,12,21)
        for xx in (5,7,9):line(xx,7,xx,17)
    elif label=='GRÖSSE':
        rect(4,4,16,16);line(8,16,16,8);line(10,8,16,8);line(16,8,16,14)
    elif label.startswith('SVG'):
        rect(2,3,5,5,1);rect(17,16,5,5,1);path=QPainterPath(QPointF(7,5));path.cubicTo(23,3,0,22,17,18);p.drawPath(path)
    elif label=='SCHNEIDEN':
        p.drawEllipse(QRectF(2,14,6,6));p.drawEllipse(QRectF(16,14,6,6));line(6,15,19,3);line(18,15,5,3)
    elif label=='TERMINAL':
        rect(2,4,20,16);line(6,8,10,12);line(10,12,6,16);line(13,16,18,16)
    elif label in ('KOPIEREN','PFAD','LINK LADEN'):
        if label=='LINK LADEN':
            rect(2,9,12,6,3);rect(10,4,12,6,3);line(8,12,16,7)
        else:rect(8,7,12,15);line(4,17,4,3);line(4,3,16,3)
    elif label in ('ZIP','ENTPACKEN','ABLAGE','EXPLORER','VERSCHIEBEN'):
        rect(2,6,20,15);line(3,6,3,3);line(3,3,10,3);line(10,3,13,6)
        if label=='ZIP':
            for yy in (9,12,15,18):line(11,yy,13,yy)
        elif label in ('VERSCHIEBEN','ENTPACKEN'):line(7,13,17,13);line(14,10,17,13);line(14,16,17,13)
    elif label in ('AUDIO LADEN','MP3','M4A','WAV','FLAC','OGG','OPUS','WMA','AIFF'):
        line(9,18,9,5);line(9,5,19,3);line(19,3,19,16);p.drawEllipse(QRectF(3,16,6,4));p.drawEllipse(QRectF(13,14,6,4))
    elif label in ('VIDEO LADEN','MP4','MOV','MKV','WEBM','AVI','WMV','GIF'):
        rect(2,4,20,16);path=QPainterPath(QPointF(10,8));path.lineTo(16,12);path.lineTo(10,16);path.closeSubpath();p.drawPath(path)
    elif label in ('PNG','JPG','WEBP','HEIC','AVIF','TIFF','BMP','STANDBILD'):
        rect(2,3,20,18);p.drawEllipse(QPointF(16,8),2,2);line(4,18,9,12);line(9,12,13,16);line(13,16,16,13);line(16,13,20,18)
    else:
        rect(5,2,14,20);line(8,8,16,8);line(8,12,16,12);line(8,16,13,16)
    p.restore()
