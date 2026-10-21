"""Saved, typed image workflows. No shell commands or arbitrary code."""
import uuid,tempfile
from pathlib import Path
from PIL import Image,ImageOps
from converter import convert,reserve
from tools import tool_outputs
from task_runtime import checkpoint,copy_stream
from batch_rename import renamed_name

KINDS=('resize','gray','rotate','compress','metadata','convert','rename')
LABELS={'resize':'Bildgröße ändern','gray':'Graustufen','rotate':'Drehen','compress':'Komprimieren','metadata':'Metadaten entfernen → PNG','convert':'Bildformat wechseln','rename':'Ausgabe benennen'}


def validate_steps(steps):
    if not isinstance(steps,list) or not 1<=len(steps)<=12:raise ValueError('Ein Ablauf benötigt 1 bis 12 Schritte.')
    clean=[]
    for i,step in enumerate(steps):
        if not isinstance(step,dict) or step.get('type') not in KINDS:raise ValueError('Ungültiger Ablaufschritt.')
        kind=step['type'];result={'type':kind}
        if kind=='resize':
            result['edge']=int(step.get('edge',1600))
            if not 1<=result['edge']<=16000:raise ValueError('Bildkante: 1 bis 16000 Pixel.')
        elif kind=='rotate':
            result['angle']=int(step.get('angle',90))
            if result['angle'] not in (90,180,270):raise ValueError('Ungültige Drehung.')
        elif kind in ('compress','convert'):
            result['format']=step.get('format','WEBP')
            if result['format'] not in ('PNG','JPG','WEBP','TIFF','BMP'):raise ValueError('Ungültiges Bildformat.')
            if kind=='compress':
                if result['format'] not in ('PNG','JPG','WEBP'):raise ValueError('Komprimieren: PNG/JPG/WebP wählen.')
                result['quality']=int(step.get('quality',82))
                if not 10<=result['quality']<=95:raise ValueError('Qualität: 10 bis 95.')
        elif kind=='rename':
            if i!=len(steps)-1:raise ValueError('Benennen muss der letzte Schritt sein.')
            result['pattern']=str(step.get('pattern','{name}_{n}'));renamed_name(Path('Beispiel.png'),result['pattern'],1)
        clean.append(result)
    return clean


def validate_workflows(items):
    if not isinstance(items,list) or len(items)>40:raise ValueError('Maximal 40 Bildabläufe.')
    result=[];names=set();ids=set()
    for item in items:
        try:name=str(item['name']).strip();identifier=str(uuid.UUID(str(item['id'])))
        except (TypeError,ValueError,KeyError,AttributeError) as error:raise ValueError('Ungültiger Ablauf.') from error
        if not 1<=len(name)<=28 or any(ord(c)<32 for c in name) or name.casefold() in names or identifier in ids:raise ValueError('Eindeutigen Namen mit höchstens 28 Zeichen verwenden.')
        result.append({'id':identifier,'name':name,'steps':validate_steps(item.get('steps'))});names.add(name.casefold());ids.add(identifier)
    return result


def run_workflow(files,steps,options):
    steps=validate_steps(steps);created=[]
    try:
        for index,file in enumerate(files):
            source=Path(file).resolve();folder=Path(options.get('output_dir') or source.parent)
            if not folder.is_dir():raise ValueError('Ausgabeordner existiert nicht.')
            with Image.open(source) as image:
                if getattr(image,'n_frames',1)>1 or image.width*image.height>80_000_000:raise ValueError('Nur Einzelbilder bis 80 Megapixel.')
            name=source.stem+'_Ablauf'
            with tempfile.TemporaryDirectory(prefix='orbit-workflow-') as tmp:
                current=source;temp_options={**options,'output_dir':tmp}
                for step_index,step in enumerate(steps):
                    checkpoint((index+(step_index/len(steps)))/len(files)*100,LABELS[step['type']]+': '+source.name);kind=step['type']
                    if kind=='rename':name=Path(renamed_name(source,step['pattern'],index+1)).stem;continue
                    if kind=='resize':
                        with Image.open(current) as original:
                            image=ImageOps.exif_transpose(original).copy();image.thumbnail((step['edge'],step['edge']),Image.Resampling.LANCZOS);current=reserve(current,'.png',Path(tmp));image.save(current,format='PNG')
                    elif kind=='gray':current=Path(tool_outputs('Bild aufbereiten',[current],{'target':'PNG','processing':{'mode':'gray'}},temp_options)[0])
                    elif kind=='rotate':current=Path(tool_outputs('Bild drehen',[current],{'angle':step['angle']},temp_options)[0])
                    elif kind=='compress':current=Path(tool_outputs('Komprimieren',[current],{'format':step['format'],'quality':step['quality']},temp_options)[0])
                    elif kind=='convert':current=Path(convert(current,step['format'],temp_options))
                    elif kind=='metadata':
                        with Image.open(current) as original:image=ImageOps.exif_transpose(original).convert('RGBA');image.info.clear()
                        current=reserve(current,'.png',Path(tmp));image.save(current,format='PNG')
                number=0
                while True:
                    output=folder/(name+('' if not number else '_'+str(number))+current.suffix)
                    try:
                        with output.open('xb'):pass
                        break
                    except FileExistsError:number+=1
                created.append(output)
                with current.open('rb') as src,output.open('wb') as dst:copy_stream(src,dst)
        checkpoint(100,'Ablauf fertig');return [str(path) for path in created]
    except Exception:
        for path in created:path.unlink(missing_ok=True)
        raise
