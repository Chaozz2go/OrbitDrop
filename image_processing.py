"""Image preparation and real SVG tracing, preserving source files."""
from pathlib import Path
import math
import xml.etree.ElementTree as ET
from PIL import Image,ImageOps,ImageEnhance,ImageFilter
from task_runtime import checkpoint

DEFAULTS={'mode':'binary','threshold':128,'auto_threshold':True,'contrast':1.0,'brightness':1.0,'blur':0.0,'invert':False,'dither':False,'max_edge':1600,'speckle':4,'simplify':1.0,'curve':'spline','colors':16,'white_background':False}

def settings(values=None):
    result={**DEFAULTS,**(values or {})}
    if result['mode'] not in ('gray','binary','color'):raise ValueError('Ungültiger Bildmodus.')
    for key,minimum,maximum in [('threshold',0,255),('max_edge',256,2400),('speckle',0,100),('colors',2,64)]:
        result[key]=int(result[key])
        if not minimum<=result[key]<=maximum:raise ValueError('Ungültiger Wert: '+key)
    for key,minimum,maximum in [('contrast',.1,3),('brightness',.1,3),('blur',0,3),('simplify',0,5)]:
        result[key]=float(result[key])
        if not math.isfinite(result[key]) or not minimum<=result[key]<=maximum:raise ValueError('Ungültiger Wert: '+key)
    if result['curve'] not in ('spline','polygon','pixel'):raise ValueError('Ungültige Konturform.')
    return result

def load_image(path):
    with Image.open(path) as source:
        if getattr(source,'n_frames',1)>1:raise ValueError('Bitte ein Einzelbild wählen.')
        if source.width*source.height>80_000_000:raise ValueError('Bild überschreitet 80 Megapixel.')
        oriented=ImageOps.exif_transpose(source).convert('RGBA')
        background=Image.new('RGBA',oriented.size,'white');background.alpha_composite(oriented)
        return background.convert('RGB')

def otsu(image):
    histogram=image.histogram();total=sum(histogram);weight=0;accumulated=0;all_sum=sum(i*n for i,n in enumerate(histogram));best=-1;threshold=128
    for i,n in enumerate(histogram):
        weight+=n;accumulated+=i*n;remaining=total-weight
        if not weight or not remaining:continue
        score=weight*remaining*(accumulated/weight-(all_sum-accumulated)/remaining)**2
        if score>best:best=score;threshold=i
    return threshold

def prepare_image(image,values=None,vector=False):
    options=settings(values);checkpoint(10,'Bild wird vorbereitet …');result=image.copy()
    if vector:result.thumbnail((options['max_edge'],options['max_edge']),Image.Resampling.LANCZOS)
    result=ImageEnhance.Brightness(result).enhance(options['brightness']);result=ImageEnhance.Contrast(result).enhance(options['contrast'])
    if options['blur']:result=result.filter(ImageFilter.GaussianBlur(options['blur']))
    if options['mode'] in ('gray','binary'):result=ImageOps.grayscale(result)
    if options['invert']:result=ImageOps.invert(result)
    threshold=options['threshold']
    if options['mode']=='binary':
        if options['auto_threshold']:threshold=otsu(result)
        if options['dither']:result=result.convert('1',dither=Image.Dither.FLOYDSTEINBERG)
        else:result=result.point(lambda pixel:255 if pixel>threshold else 0,mode='1')
    checkpoint(35,'Bildvorbereitung fertig');return result,threshold

def trace_svg(image,values,original_size):
    import vtracer
    options=settings(values);rgba=image.convert('RGBA');checkpoint(40,'Konturen werden vektorisiert …')
    cfg=vtracer.Config(clustering='bw' if options['mode']=='binary' else 'color-cluster',mode=options['curve'],filter_speckle=options['speckle'],simplify=options['simplify'],max_colors=options['colors'],binary_threshold=128,path_precision=2)
    svg=cfg.convert_pixels(rgba.tobytes(),rgba.width,rgba.height)
    checkpoint(90,'SVG wird gespeichert …');root=ET.fromstring(svg);namespace='http://www.w3.org/2000/svg';ET.register_namespace('',namespace)
    root.set('viewBox',f'0 0 {rgba.width} {rgba.height}');root.set('width',str(original_size[0]));root.set('height',str(original_size[1]))
    if options['white_background']:
        root.insert(0,ET.Element('{'+namespace+'}rect',{'width':str(rgba.width),'height':str(rgba.height),'fill':'white'}))
    return ET.tostring(root,encoding='unicode',xml_declaration=True)

def process_image(source,target,values,output):
    original=load_image(source);options=settings(values);prepared,threshold=prepare_image(original,options,vector=target=='SVG')
    if target=='SVG':Path(output).write_text(trace_svg(prepared,options,original.size),encoding='utf-8')
    elif target=='BITMAP':
        if prepared.mode!='1':raise ValueError('Für eine 1-Bit-Bitmap bitte Schwarzweiß wählen.')
        prepared.save(output,format='BMP')
    elif target=='PNG':prepared.save(output,format='PNG')
    else:raise ValueError('Unbekanntes Bildziel.')
    checkpoint(100,'Bild gespeichert');return threshold
