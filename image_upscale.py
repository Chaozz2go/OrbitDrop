"""Conventional resampling, gentle denoising and sharpening; no models/network."""
from pathlib import Path
import math
from PIL import Image,ImageOps,ImageFilter
from photo_effects import adjust_photo
from task_runtime import checkpoint

METHODS={'lanczos':Image.Resampling.LANCZOS,'bicubic':Image.Resampling.BICUBIC,'nearest':Image.Resampling.NEAREST}

def upscale_settings(values=None):
    result={'factor':2.,'width':0,'height':0,'method':'lanczos','denoise':False,'sharpen':0,**(values or {})}
    result['factor']=float(result['factor']);result['width']=int(result['width']);result['height']=int(result['height']);result['sharpen']=int(result['sharpen'])
    if not math.isfinite(result['factor']) or not 1<=result['factor']<=8 or result['method'] not in METHODS or not 0<=result['sharpen']<=200:raise ValueError('Ungültige Vergrößerungsoption.')
    if not 0<=result['width']<=30000 or not 0<=result['height']<=30000:raise ValueError('Zielkante muss zwischen 0 und 30000 Pixeln liegen.')
    if result['method']=='nearest':result['denoise']=False;result['sharpen']=0
    return result

def target_size(size,values):
    v=upscale_settings(values);w,h=v['width'],v['height']
    scale=min(w/size[0] if w else float('inf'),h/size[1] if h else float('inf')) if w or h else v['factor']
    result=(max(1,round(size[0]*scale)),max(1,round(size[1]*scale)))
    if max(result)>30000 or result[0]*result[1]>80_000_000:raise ValueError('Zielbild überschreitet 80 Megapixel oder 30000 Pixel Kantenlänge. Bitte kleineren Faktor wählen.')
    if not 1<=scale<=8:raise ValueError('Vergrößerung muss zwischen 1× und 8× liegen. Für kleinere Bilder die normale Größenänderung verwenden.')
    return result

def prepare_source(path,edit=None):
    with Image.open(path) as source:
        if getattr(source,'n_frames',1)>1 or source.width*source.height>80_000_000:raise ValueError('Bitte ein Einzelbild bis 80 Megapixel wählen.')
        image=ImageOps.exif_transpose(source).convert('RGBA')
    edit=edit or {};angle=int(edit.get('angle',0))%360
    if angle not in (0,90,180,270):raise ValueError('Ungültige Bilddrehung.')
    if angle:image=image.rotate(-angle,expand=True)
    if edit.get('crop'):
        left,top,right,bottom=map(int,edit['crop'])
        if not 0<=left<right<=image.width or not 0<=top<bottom<=image.height:raise ValueError('Ungültiger Ausschnitt.')
        image=image.crop((left,top,right,bottom))
    return adjust_photo(image,edit.get('adjustments'))

def enlarge(image,values=None):
    v=upscale_settings(values);size=target_size(image.size,v);image=image.convert('RGBA');checkpoint(20,'Bild wird vorbereitet …')
    if v['denoise']:
        color=image.convert('RGB').filter(ImageFilter.MedianFilter(3));color.putalpha(image.getchannel('A'));image=color
    checkpoint(40,'Bild wird interpoliert …');result=image.resize(size,METHODS[v['method']])
    if v['sharpen']:
        color=result.convert('RGB').filter(ImageFilter.UnsharpMask(radius=1.2,percent=v['sharpen'],threshold=3));color.putalpha(result.getchannel('A'));result=color
    checkpoint(90,'Vergrößertes Bild wird gespeichert …');return result

def export_upscale(path,values,edit=None,options=None,expected=None):
    from converter import reserve
    from preview_runtime import source_key
    if expected is not None and source_key('upscale',path)!=tuple(expected):raise ValueError('Bild seit der Vorschau geändert. Bitte erneut öffnen.')
    image=prepare_source(path,edit)
    if expected is not None and source_key('upscale',path)!=tuple(expected):raise ValueError('Bild während des Ladens geändert. Bitte erneut öffnen.')
    result=enlarge(image,values);output=reserve(Path(path).with_name(Path(path).stem+'_upscaled.png'),'.png',(options or {}).get('output_dir'))
    try:result.save(output,format='PNG');checkpoint(100,'Bild vergrößert');return [str(output)]
    except Exception:output.unlink(missing_ok=True);raise
