"""Shared preview/export color adjustments; preserve alpha and original files."""
import math
from PIL import Image,ImageEnhance,ImageOps

DEFAULTS={'brightness':1.,'contrast':1.,'saturation':1.,'sharpness':1.,'warmth':0.,'grayscale':False}


def photo_settings(values=None):
    values={**DEFAULTS,**(values or {})}
    for key,low,high in [('brightness',.1,3),('contrast',.1,3),('saturation',0,3),('sharpness',0,3),('warmth',-100,100)]:
        values[key]=float(values[key])
        if not math.isfinite(values[key]) or not low<=values[key]<=high:raise ValueError('Ungültige Bildkorrektur: '+key)
    values['grayscale']=bool(values['grayscale']);return values


def adjust_photo(image,values=None):
    values=photo_settings(values);rgba=image.convert('RGBA');alpha=rgba.getchannel('A');result=rgba.convert('RGB')
    for key,enhancer in [('brightness',ImageEnhance.Brightness),('contrast',ImageEnhance.Contrast),('saturation',ImageEnhance.Color),('sharpness',ImageEnhance.Sharpness)]:
        if values[key]!=1:result=enhancer(result).enhance(values[key])
    if values['warmth']:
        amount=values['warmth']/500;red,green,blue=result.split()
        red=red.point([min(255,max(0,round(n*(1+amount)))) for n in range(256)])
        blue=blue.point([min(255,max(0,round(n*(1-amount)))) for n in range(256)]);result=Image.merge('RGB',(red,green,blue))
    if values['grayscale']:result=ImageOps.grayscale(result).convert('RGB')
    result.putalpha(alpha);return result


def resize_photo(image,values):
    width,height=int(values.get('width',0)),int(values.get('height',0))
    if width<0 or height<0:raise ValueError('Bildkanten dürfen nicht negativ sein.')
    if not (width or height):return image
    if values.get('keep_ratio',True):
        scale=min(width/image.width if width else float('inf'),height/image.height if height else float('inf'))
        size=(max(1,round(image.width*scale)),max(1,round(image.height*scale)))
    else:size=(width or image.width,height or image.height)
    if size[0]*size[1]>80_000_000:raise ValueError('Zielbild überschreitet 80 Megapixel.')
    return image.resize(size,Image.Resampling.LANCZOS)
