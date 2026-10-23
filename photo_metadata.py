"""Bounded folder expansion and EXIF-based rename plans; never alter folders."""
from datetime import datetime
from pathlib import Path
import os,re
from PIL import Image
from archives import _linklike
from batch_rename import valid_name,validate_pairs,signature
from task_runtime import checkpoint

TOKENS={'name','n','date','time','year','month','day','camera'}
DATE_FORMATS=('%Y-%m-%d','%Y%m%d','%d-%m-%Y')

def collect_files(inputs,recursive=False,images_only=False):
    result=[];seen=set();ignored=0;visited=0
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:pass
    Image.init();extensions={ext for ext,kind in Image.registered_extensions().items() if kind in Image.OPEN}
    def add(path):
        nonlocal ignored,visited
        checkpoint(message='Ordnerinhalt wird gelesen …');visited+=1
        if visited>100000:raise ValueError('Bitte einen kleineren Ordner auswählen (max. 100000 geprüfte Einträge).')
        if _linklike(path) or not path.is_file():ignored+=1;return
        if images_only and path.suffix.lower() not in extensions:ignored+=1;return
        key=str(path.absolute()).casefold()
        if key not in seen:seen.add(key);result.append(path.absolute())
        if len(result)>10000:raise ValueError('Maximal 10000 Dateien pro Umbenennung.')
    for item in inputs:
        root=Path(item).absolute()
        if _linklike(root):raise ValueError('Verknüpfungen/Junctions bitte nicht als Quelle wählen.')
        if root.is_dir():
            for parent,dirs,files in os.walk(root,followlinks=False):
                dirs[:]=sorted(d for d in dirs if not _linklike(Path(parent)/d)) if recursive else []
                for name in sorted(files):add(Path(parent)/name)
        else:add(root)
    if not result:raise ValueError('Keine passenden Dateien im gewählten Bereich gefunden.')
    return result,ignored

def image_metadata(path):
    date=None;camera='Kamera_unbekannt'
    try:
        with Image.open(path) as image:
            exif=image.getexif();camera=str(exif.get(272) or camera).strip()
            raw=exif.get(36867)
            if not raw:
                try:raw=exif.get_ifd(34665).get(36867)
                except (KeyError,ValueError,TypeError):pass
            if isinstance(raw,bytes):raw=raw.decode('ascii',errors='replace')
            if raw:
                try:date=datetime.strptime(str(raw).strip('\x00 ').strip(),'%Y:%m:%d %H:%M:%S')
                except ValueError:pass
    except (OSError,ValueError,SyntaxError):pass
    camera=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',camera).rstrip(' .')[:100] or 'Kamera_unbekannt'
    return date,camera

def metadata_plan(files,pattern,start=1,digits=3,date_format='%Y-%m-%d',missing='skip',collision='number'):
    if date_format not in DATE_FORMATS or missing not in ('skip','keep','mtime') or collision not in ('number','error'):raise ValueError('Ungültige Umbenennungsoption.')
    if not pattern.strip() or not 1<=digits<=8 or not 0<=start<=99_999_999:raise ValueError('Ungültiges Muster oder Nummerierung.')
    tokens=re.findall(r'\{([^{}]+)\}',pattern)
    if any(t not in TOKENS for t in tokens) or re.search('[{}]',re.sub(r'\{[^{}]+\}','',pattern)):raise ValueError('Erlaubt: '+', '.join('{'+t+'}' for t in sorted(TOKENS)))
    needs_date=bool(set(tokens)&{'date','time','year','month','day'});items=[];skipped=[]
    for index,source in enumerate(files):
        source=Path(source);checkpoint(index/max(1,len(files))*100,'Metadaten: '+source.name);stamp=signature(source)
        date,camera=image_metadata(source) if needs_date or 'camera' in tokens else (None,'Kamera_unbekannt')
        origin='EXIF-Aufnahmedatum' if date else ''
        if needs_date and date is None:
            if missing=='mtime':date=datetime.fromtimestamp(source.stat().st_mtime);origin='Änderungsdatum (Ersatz)'
            else:
                skipped.append((source,source,'EXIF fehlt · '+('Originalname behalten' if missing=='keep' else 'übersprungen')));continue
        number=start+len(items)
        if number>99_999_999:raise ValueError('Nummerierung überschreitet acht Stellen.')
        values={'name':source.stem,'n':str(number).zfill(digits),'camera':camera}
        if date:values.update(date=date.strftime(date_format),time=date.strftime('%H-%M-%S'),year=f'{date.year:04}',month=f'{date.month:02}',day=f'{date.day:02}')
        name=valid_name(re.sub(r'\{([^{}]+)\}',lambda m:values[m[1]],pattern)+source.suffix)
        if signature(source)!=stamp:raise ValueError('Datei während des Lesens geändert: '+str(source))
        items.append((source,source.with_name(name),origin or 'Namensmuster'))
    if not items:return [],skipped
    source_names={str(s.absolute()).casefold() for s,_,_ in items};used=set();pairs=[];rows=[]
    occupied={str(p.absolute()).casefold() for folder in {t.parent for _,t,_ in items} for p in folder.iterdir()}-source_names
    for source,target,origin in items:
        initial=target;count=1
        while True:
            key=str(target.absolute()).casefold()
            existing=key in occupied
            if key not in used and not existing:break
            if collision=='error':raise FileExistsError('Zielname bereits belegt: '+str(target))
            count+=1;target=initial.with_name(initial.stem+'_'+str(count)+initial.suffix)
        used.add(key);pairs.append((source,target));rows.append((source,target,origin+(' · Nummer ergänzt' if target!=initial else '')))
    return validate_pairs(pairs),rows+skipped
