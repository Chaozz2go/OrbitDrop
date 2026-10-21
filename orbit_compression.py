"""Local compression with verified size limits and exclusive output files."""
import io,json,math,os,tempfile
from pathlib import Path
from PIL import Image,ImageOps
from converter import reserve
from filetypes import inspect_file,backend,run
from task_runtime import checkpoint

DEFAULTS={'format':'WEBP','quality':82,'max_edge':0,'target_mb':0.,'video_height':0,'audio_kbps':128}


def compression_settings(values=None):
    p={**DEFAULTS,**(values or {})}
    if p['format'] not in ('WEBP','JPG','PNG'):raise ValueError('Ungültiges Bildformat.')
    for key,low,high in [('quality',10,95),('max_edge',0,16000),('video_height',0,2160),('audio_kbps',32,320)]:
        p[key]=int(p[key])
        if not low<=p[key]<=high:raise ValueError('Ungültiger Wert: '+key)
    p['target_mb']=float(p['target_mb'])
    if not math.isfinite(p['target_mb']) or not 0<=p['target_mb']<=10000:raise ValueError('Ungültige Zielgröße.')
    return p


def image_bytes(source,values=None):
    p=compression_settings(values)
    with Image.open(source) as original:
        if getattr(original,'n_frames',1)>1:raise ValueError('Bitte ein Einzelbild wählen.')
        if original.width*original.height>80_000_000:raise ValueError('Bild überschreitet 80 Megapixel.')
        image=ImageOps.exif_transpose(original).convert('RGBA');image.info.clear()
    if p['max_edge']:image.thumbnail((p['max_edge'],p['max_edge']),Image.Resampling.LANCZOS)
    # Fresh image strips source metadata. JPEG explicitly receives a white background.
    if p['format']=='JPG':
        flat=Image.new('RGB',image.size,'white');flat.paste(image,mask=image.getchannel('A'));image=flat
    def encode(quality):
        checkpoint(message='Bildqualität wird berechnet …');buffer=io.BytesIO()
        image.save(buffer,format='JPEG' if p['format']=='JPG' else p['format'],**({'optimize':True} if p['format']=='PNG' else {'quality':quality}))
        return buffer.getvalue()
    target=max(1,int(p['target_mb']*1_000_000)) if p['target_mb'] else 0;quality=p['quality'];data=encode(quality)
    if target and len(data)>target:
        if p['format']=='PNG':raise ValueError('PNG erreicht die Zielgröße nicht. WebP/JPG oder eine kleinere Bildkante wählen.')
        low,high=10,quality-1;best=None
        while low<=high:
            mid=(low+high)//2;candidate=encode(mid)
            if len(candidate)<=target:best=(candidate,mid);low=mid+1
            else:high=mid-1
        if best is None:raise ValueError('Zielgröße nicht erreichbar. Bildkante weiter reduzieren oder Zielgröße erhöhen.')
        data,quality=best
    return data,quality,image.size


def probe_media(source):
    if not backend('ffmpeg') or not backend('ffprobe'):raise ValueError('FFmpeg und FFprobe werden benötigt.')
    result=run([backend('ffprobe'),'-v','error','-protocol_whitelist','file,pipe','-show_format','-show_streams','-of','json',str(source)],timeout=30)
    if result.returncode:raise ValueError(result.stderr[-500:] or 'Medienprüfung fehlgeschlagen.')
    info=json.loads(result.stdout)
    try:duration=float(info['format']['duration'])
    except (ValueError,KeyError):raise ValueError('Dauer der Datei konnte nicht bestimmt werden.')
    if not math.isfinite(duration) or duration<=0:raise ValueError('Ungültige Mediendauer.')
    return duration,any(s.get('codec_type')=='audio' for s in info.get('streams',[]))


def compress_media(source,output,kind,p):
    duration,audio=probe_media(source);target=int(p['target_mb']*1_000_000)
    common=[backend('ffmpeg'),'-hide_banner','-loglevel','error','-nostdin','-y','-protocol_whitelist','file,pipe','-i',str(source)]
    if kind=='Audio':
        bitrate=p['audio_kbps']
        if target:
            budget=int(target*8/duration*.90/1000)
            choices=[v for v in (32,40,48,56,64,80,96,112,128,160,192,224,256,320) if v<=min(budget,bitrate)]
            if not choices:raise ValueError('Zielgröße für diese Audiodauer zu klein.')
            bitrate=max(choices)
        args=common+['-map','0:a:0','-vn','-map_metadata','-1','-c:a','libmp3lame','-b:a',str(bitrate)+'k',str(output)]
        result=run(args,timeout=7200,duration=duration)
    else:
        height=p['video_height'];vf=(f'scale=-2:min({height}\\,ih),' if height else '')+'pad=ceil(iw/2)*2:ceil(ih/2)*2'
        video=['-map','0:V:0','-vf',vf,'-c:v','libx264','-pix_fmt','yuv420p','-preset','medium']
        tail=['-map','0:a:0?','-c:a','aac','-b:a','96k','-map_metadata','-1','-movflags','+faststart',str(output)]
        if target:
            bitrate=int(target*8/duration*.94)-(96000 if audio else 0)
            if bitrate<20000:raise ValueError('Zielgröße für diese Videodauer zu klein. Auflösung reduzieren oder Zielgröße erhöhen.')
            with tempfile.TemporaryDirectory(prefix='orbit-pass-') as temp:
                flags=['-b:v',str(bitrate),'-passlogfile',str(Path(temp)/'video')]
                first=run(common+video+flags+['-pass','1','-an','-f','null',os.devnull],timeout=7200,duration=duration)
                if first.returncode:raise ValueError(first.stderr[-1000:] or 'Erster Videodurchlauf fehlgeschlagen.')
                result=run(common+video+flags+['-pass','2']+tail,timeout=7200,duration=duration)
        else:
            crf=round(36-(p['quality']-10)/85*18)
            result=run(common+video+['-crf',str(crf)]+tail,timeout=7200,duration=duration)
    if result.returncode or not output.stat().st_size:raise ValueError(result.stderr[-1000:] or 'Komprimierung fehlgeschlagen.')
    if target and output.stat().st_size>target:raise ValueError('Die fertige Datei überschreitet die Zielgröße. Zielgröße erhöhen oder Auflösung reduzieren; kein übergroßes Ergebnis gespeichert.')


def compress_files(files,values,options):
    p=compression_settings(values);created=[]
    try:
        for index,file in enumerate(files):
            source=Path(file).resolve();checkpoint(index/max(1,len(files))*100,'Komprimieren: '+source.name)
            kind=inspect_file(source).kind
            suffix={ 'Bild':{'WEBP':'.webp','JPG':'.jpg','PNG':'.png'}[p['format']],'Video':'.mp4','Audio':'.mp3','PDF':'.pdf'}.get(kind)
            if not suffix:raise ValueError(source.name+': Komprimieren wird für diesen Dateityp nicht angeboten.')
            folder=Path(options['output_dir']) if options.get('output_dir') else source.parent
            output=reserve(source.with_name(source.stem+'_kleiner'+suffix),suffix,folder);created.append(output)
            if kind=='Bild':output.write_bytes(image_bytes(source,p)[0])
            elif kind=='PDF':
                import pymupdf
                with pymupdf.open(source) as pdf:
                    if pdf.needs_pass:raise ValueError('Verschlüsseltes PDF wird nicht unterstützt.')
                    # Reserve owns this empty path; PyMuPDF writes into it.
                    pdf.save(output,garbage=4,deflate=True,clean=True)
                if p['target_mb'] and output.stat().st_size>p['target_mb']*1_000_000:raise ValueError('Verlustfreie PDF-Komprimierung erreicht die Zielgröße nicht.')
            else:compress_media(source,output,kind,p)
        checkpoint(100,'Komprimierung fertig');return [str(p) for p in created]
    except Exception:
        for path in created:path.unlink(missing_ok=True)
        raise
