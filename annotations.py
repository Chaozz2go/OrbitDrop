"""Flatten manual marks into pixels. Solid redaction is always opaque."""
import math,os
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

KINDS=('redact','arrow','rectangle','text')


def validate_marks(marks,size):
    if not isinstance(marks,list) or len(marks)>200:raise ValueError('Maximal 200 Markierungen sind erlaubt.')
    result=[];width,height=size
    for item in marks:
        kind=item.get('kind')
        if kind not in KINDS:raise ValueError('Unbekannte Markierung.')
        coords=[float(item[k]) for k in ('x1','y1','x2','y2')]
        if any(not math.isfinite(v) for v in coords):raise ValueError('Ungültige Koordinaten.')
        if not all(0<=v<=limit for v,limit in zip(coords,(width,height,width,height))):raise ValueError('Markierung außerhalb des Bildes.')
        color=str(item.get('color','#ff6b5e'))
        if len(color)!=7 or color[0]!='#' or any(c not in '0123456789abcdefABCDEF' for c in color[1:]):raise ValueError('Ungültige Markierungsfarbe.')
        stroke=float(item.get('stroke',4));font_size=float(item.get('font_size',28));text=str(item.get('text',''))
        if not math.isfinite(stroke) or not 1<=stroke<=100 or not math.isfinite(font_size) or not 6<=font_size<=500 or len(text)>500:raise ValueError('Ungültige Markierungsgröße / Textlänge.')
        result.append(dict(kind=kind,x1=coords[0],y1=coords[1],x2=coords[2],y2=coords[3],color=color,stroke=stroke,font_size=font_size,text=text))
    return result


def annotation_font(size):
    for name in (str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts/arial.ttf'),'DejaVuSans.ttf'):
        try:return ImageFont.truetype(name,size)
        except OSError:pass
    return ImageFont.load_default(size=size)


def render_marks(image,marks,original_size=None):
    original_size=original_size or image.size;marks=validate_marks(marks,original_size);result=image.convert('RGBA').copy();draw=ImageDraw.Draw(result)
    sx,sy=result.width/original_size[0],result.height/original_size[1];scale=min(sx,sy)
    for item in marks:
        x1,y1,x2,y2=item['x1']*sx,item['y1']*sy,item['x2']*sx,item['y2']*sy
        box=(min(x1,x2),min(y1,y2),max(x1,x2),max(y1,y2));stroke=max(1,round(item['stroke']*scale));color=item['color'];kind=item['kind']
        if kind=='redact':draw.rectangle(box,fill=(0,0,0,255))
        elif kind=='rectangle':draw.rectangle(box,outline=color,width=stroke)
        elif kind=='text':draw.text((x1,y1),item['text'],font=annotation_font(max(1,round(item['font_size']*scale))),fill=color,stroke_width=0)
        else:
            draw.line((x1,y1,x2,y2),fill=color,width=stroke);angle=math.atan2(y2-y1,x2-x1);length=max(10*scale,stroke*4)
            points=[(x2,y2),(x2-length*math.cos(angle-.5),y2-length*math.sin(angle-.5)),(x2-length*math.cos(angle+.5),y2-length*math.sin(angle+.5))];draw.polygon(points,fill=color)
    # Fresh RGBA contains no source EXIF, thumbnails, layers or hidden original image.
    clean=Image.new('RGBA',result.size);clean.paste(result);return clean
