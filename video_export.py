import json
from pathlib import Path
import tempfile
from converter import reserve
from filetypes import backend,run,inspect_file
from task_runtime import checkpoint,current,copy_stream


def export_video(source,parameters,options):
    source=Path(source).resolve();info=inspect_file(source)
    if info.kind!='Video' or 'MP4' not in info.actions:raise ValueError('Für den MP4-Export werden FFmpeg/FFprobe mit H.264-Unterstützung benötigt.')
    probe=run([backend('ffprobe'),'-v','error','-protocol_whitelist','file,pipe','-show_entries','format=duration','-of','json',str(source)],timeout=30)
    try:
        from edit_models import video_duration
        duration=video_duration(source)
    except (ValueError,KeyError):raise ValueError('Videodauer konnte nicht gelesen werden.')
    ranges=[(float(start),float(end)) for start,end in parameters.get('ranges',[(0,duration)])]
    if not ranges or any(start<0 or end<=start or end>duration+.1 for start,end in ranges):raise ValueError('Ungültige Videoabschnitte.')
    if any(ranges[i][0]<ranges[i-1][1]-1e-7 for i in range(1,len(ranges))):raise ValueError('Abschnitte dürfen sich nicht überlappen.')
    folder=Path(options['output_dir']) if options.get('output_dir') else source.parent
    if not folder.is_dir():raise ValueError('Ausgabeordner existiert nicht.')
    angle=int(parameters.get('angle',0))%360
    rotation={0:[],90:['transpose=1'],180:['hflip','vflip'],270:['transpose=2']}.get(angle)
    if rotation is None:raise ValueError('Drehung muss ein Vielfaches von 90° sein.')
    height=int(options.get('video_height',0));filters=rotation[:]
    if height:filters.append(f'scale=-2:min({height}\\,ih)')
    filters.append('pad=ceil(iw/2)*2:ceil(ih/2)*2')
    crf={'Hohe Qualität':18,'Ausgewogen':23,'Kleine Datei':28}.get(options.get('video_profile'),23)
    outputs=[];control=current();old_base=control.base if control else 0;old_span=control.span if control else 100
    total=sum(end-start for start,end in ranges);completed=0
    try:
        with tempfile.TemporaryDirectory(prefix='orbit-video-') as temp:
            root=Path(temp);parts=[]
            for index,(start,end) in enumerate(ranges):
                if control:control.base=completed/total*90;control.span=(end-start)/total*90
                checkpoint(0,f'Abschnitt {index+1}/{len(ranges)} wird geschnitten …')
                part=root/f'part{index:05}.mp4';parts.append(part)
                args=[backend('ffmpeg'),'-hide_banner','-loglevel','error','-nostdin','-y','-protocol_whitelist','file,pipe','-ss',str(start),'-i',str(source),'-t',str(end-start),'-map','0:V:0','-map','0:a:0?','-c:v','libx264','-pix_fmt','yuv420p','-vf',','.join(filters),'-fps_mode','vfr','-crf',str(crf),'-c:a','aac','-movflags','+faststart',str(part)]
                result=run(args,timeout=7200,duration=end-start)
                if result.returncode or not part.is_file() or not part.stat().st_size:raise ValueError(result.stderr[-1000:] or 'Abschnitt konnte nicht erstellt werden.')
                completed+=end-start
            if control:control.base=90;control.span=10
            if parameters.get('separate',False):
                for index,part in enumerate(parts):
                    checkpoint(index/len(parts)*100,'Abschnitt wird gespeichert …')
                    output=reserve(source.with_name(source.stem+f'_Teil_{index+1:04}.mp4'),'.mp4',folder);outputs.append(output)
                    with part.open('rb') as inp,output.open('wb') as out:copy_stream(inp,out,part.stat().st_size)
            else:
                output=reserve(source.with_name(source.stem+'_Schnitt.mp4'),'.mp4',folder);outputs.append(output)
                if len(parts)==1:
                    with parts[0].open('rb') as inp,output.open('wb') as out:copy_stream(inp,out,parts[0].stat().st_size)
                else:
                    manifest=root/'parts.txt';manifest.write_text(''.join("file '"+part.name+"'\n" for part in parts),encoding='utf-8')
                    result=run([backend('ffmpeg'),'-hide_banner','-loglevel','error','-nostdin','-y','-protocol_whitelist','file,pipe','-f','concat','-safe','1','-i',str(manifest),'-c','copy','-movflags','+faststart',str(output)],timeout=7200,duration=total)
                    if result.returncode or not output.stat().st_size:raise ValueError(result.stderr[-1000:] or 'Abschnitte konnten nicht zusammengefügt werden.')
            checkpoint(100,'Videoschnitt gespeichert')
        return [str(path) for path in outputs]
    except Exception:
        for path in outputs:path.unlink(missing_ok=True)
        raise
    finally:
        if control:control.base=old_base;control.span=old_span
