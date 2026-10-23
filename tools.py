"""Non-destructive image, PDF and clip tools."""
import json
from pathlib import Path
import shutil
from PIL import Image,ImageOps
from converter import reserve
from extended import convert_picture
from filetypes import backend,run,inspect_file
from task_runtime import checkpoint

TOOLS=('Bildgröße ändern','Bild drehen','PDFs zusammenfügen','PDF aufteilen','Video kürzen')


def page_indices(text,count):
    if not text.strip():return list(range(count))
    result=[]
    try:
        for part in text.split(','):
            part=part.strip()
            if '-' in part:
                first,last=[int(value) for value in part.split('-')]
                if first>last:raise ValueError()
                values=range(first,last+1)
            else:values=[int(part)]
            for number in values:
                if not 1<=number<=count:raise ValueError()
                if number-1 not in result:result.append(number-1)
    except ValueError:raise ValueError(f'Seiten bitte als 1-3,5 angeben; gültig sind 1 bis {count}.')
    return result


def tool_outputs(action,files,parameters,options):
    sources=[Path(file).resolve() for file in files]
    if not sources:raise ValueError('Bitte mindestens eine Datei auswählen.')
    folder=Path(options['output_dir']) if options.get('output_dir') else sources[0].parent
    if not folder.is_dir():raise ValueError('Ausgabeordner existiert nicht.')
    checkpoint(0,'Werkzeug wird vorbereitet …')
    created=[]
    try:
        if action=='Audio verbessern':
            from audio_tools import improve_audio
            return improve_audio(sources,parameters,options)
        if action=='OCR PDF':
            from local_ocr import ocr_pdf
            return ocr_pdf(sources,parameters,options)
        if action=='Bildablauf':
            from workflows import run_workflow
            return run_workflow(sources,parameters['steps'],options)
        if action=='PDF-Seiten':
            from pdf_pages import export_pages
            if len(sources)!=1:raise ValueError('Bitte ein PDF wählen.')
            return export_pages(sources[0],parameters['entries'],options,parameters.get('signature'))
        if action=='Komprimieren':
            from orbit_compression import compress_files
            return compress_files(sources,parameters,options)
        if action=='Bild markieren':
            from annotations import render_marks
            if len(sources)!=1:raise ValueError('Bitte genau ein Bild auswählen.')
            with Image.open(sources[0]) as original:
                if getattr(original,'n_frames',1)>1 or original.width*original.height>80_000_000:raise ValueError('Bitte ein Einzelbild bis 80 Megapixel wählen.')
                image=render_marks(ImageOps.exif_transpose(original),parameters.get('marks',[]))
                output=reserve(sources[0].with_name(sources[0].stem+'_markiert.png'),'.png',folder);created.append(output);image.save(output,format='PNG')
            checkpoint(100,'Markiertes Bild gespeichert');return [str(output)]
        if action=='Bild aufbereiten':
            from image_processing import process_image
            target=parameters.get('target','PNG')
            if target not in ('PNG','BITMAP','SVG'):raise ValueError('Ungültiges Bildziel.')
            for source in sources:
                output=reserve(source,{'PNG':'.png','BITMAP':'.bmp','SVG':'.svg'}[target],folder);created.append(output)
                process_image(source,target,parameters.get('processing',{}),output)
            return [str(p) for p in created]
        if action=='Audio bearbeiten':
            from audio_export import export_audio
            if len(sources)!=1:raise ValueError('Bitte genau eine Audiodatei wählen.')
            return export_audio(sources[0],parameters,options)
        if action in ('Video bearbeiten','Video drehen'):
            from video_export import export_video
            if len(sources)!=1:raise ValueError('Bitte genau ein Video auswählen.')
            return export_video(sources[0],parameters,options)
        if action=='Bild vergrößern':
            from image_upscale import export_upscale
            if len(sources)!=1:raise ValueError('Bitte genau ein Bild auswählen.')
            return export_upscale(sources[0],parameters.get('upscale',{}),parameters.get('edit'),options,parameters.get('source_signature'))
        if action=='Bild bearbeiten':
            if len(sources)!=1:raise ValueError('Bitte genau ein Bild auswählen.')
            with Image.open(sources[0]) as original:
                if getattr(original,'n_frames',1)>1:raise ValueError('Nur Einzelbilder können zugeschnitten werden.')
                if original.width*original.height>80_000_000:raise ValueError('Bild überschreitet 80 Megapixel.')
                image=ImageOps.exif_transpose(original)
                angle=int(parameters.get('angle',0))%360
                if angle not in (0,90,180,270):raise ValueError('Ungültige Bilddrehung.')
                if angle:image=image.rotate(-angle,expand=True)
                crop=parameters.get('crop')
                if crop:
                    left,top,right,bottom=map(int,crop)
                    if not (0<=left<right<=image.width and 0<=top<bottom<=image.height):raise ValueError('Ausschnitt liegt außerhalb des Bilds.')
                    image=image.crop((left,top,right,bottom))
                from photo_effects import adjust_photo,resize_photo
                image=adjust_photo(image,parameters.get('adjustments'))
                image=resize_photo(image,parameters.get('resize',{}))
                checkpoint(50,'Bild wird bearbeitet …')
                output=reserve(sources[0],'.png',folder);created.append(output);image.save(output,format='PNG')
            checkpoint(100,'Bild gespeichert');return [str(output)]
        if action in ('Bildgröße ändern','Bild drehen'):
            for index,source in enumerate(sources):
                checkpoint(index/len(sources)*100,source.name)
                info=inspect_file(source)
                if info.kind!='Bild':raise ValueError(source.name+': kein unterstütztes Einzelbild.')
                with Image.open(source) as original:
                    if getattr(original,'n_frames',1)>1:raise ValueError('Mehrseitige Bilder noch nicht unterstützt.')
                    image=ImageOps.exif_transpose(original)
                    if action=='Bildgröße ändern':
                        width,height=int(parameters.get('width',0)),int(parameters.get('height',0))
                        if width<0 or height<0 or not (width or height):raise ValueError('Mindestens eine Bildkante muss größer als 0 sein.')
                        if parameters.get('keep_ratio',True):
                            ratio=min(width/image.width if width else float('inf'),height/image.height if height else float('inf'))
                            size=(max(1,round(image.width*ratio)),max(1,round(image.height*ratio)))
                        else:size=(width or image.width,height or image.height)
                        if size[0]*size[1]>80_000_000:raise ValueError('Zielbild überschreitet 80 Megapixel.')
                        image=image.resize(size,Image.Resampling.LANCZOS)
                    else:image=image.rotate(-int(parameters.get('angle',90)),expand=True)
                    output=reserve(source,'.png',folder);created.append(output)
                    image.save(output,format='PNG')
            checkpoint(100,'Bilder fertig')
        elif action in ('PDFs zusammenfügen','PDF aufteilen'):
            import pymupdf
            if action=='PDFs zusammenfügen':
                output=reserve(sources[0].with_name('Zusammengefuegt.pdf'),'.pdf',folder);created.append(output)
                with pymupdf.open() as result:
                    for index,source in enumerate(sources):
                        checkpoint(index/len(sources)*100,'PDF hinzufügen: '+source.name)
                        with pymupdf.open(source) as doc:
                            if doc.needs_pass:raise ValueError('Verschlüsseltes PDF: '+source.name)
                            if not doc.is_pdf:raise ValueError('Keine PDF-Datei: '+source.name)
                            result.insert_pdf(doc)
                    if not len(result):raise ValueError('Keine PDF-Seiten gefunden.')
                    result.save(output)
            else:
                for file_index,source in enumerate(sources):
                    with pymupdf.open(source) as doc:
                        if doc.needs_pass or not doc.is_pdf:raise ValueError('Kein unverschlüsseltes PDF: '+source.name)
                        indices=page_indices(parameters.get('pages',''),len(doc))
                        for index,page in enumerate(indices):
                            checkpoint((file_index+index/max(1,len(indices)))/len(sources)*100,f'{source.name}: Seite {page+1}')
                            output=reserve(source.with_name(source.stem+f'_Seite_{page+1:04}.pdf'),'.pdf',folder);created.append(output)
                            with pymupdf.open() as result:
                                result.insert_pdf(doc,from_page=page,to_page=page);result.save(output)
            checkpoint(100,'PDF fertig')
        elif action=='Video kürzen':
            if len(sources)!=1:raise ValueError('Zum Kürzen bitte genau ein Video auswählen.')
            source=sources[0];info=inspect_file(source)
            if info.kind!='Video' or 'MP4' not in info.actions:raise ValueError('Videokonverter fehlt oder diese Datei kann nicht als MP4 ausgegeben werden.')
            start,end=float(parameters.get('start',0)),float(parameters.get('end',0))
            if start<0 or end<=start:raise ValueError('Ende muss nach Start liegen (Sekunden).')
            probe=run([backend('ffprobe'),'-v','error','-protocol_whitelist','file,pipe','-show_entries','format=duration','-of','json',str(source)],timeout=30)
            try:duration=float(json.loads(probe.stdout)['format']['duration'])
            except (ValueError,KeyError):duration=None
            if duration and (start>=duration or end>duration+.05):raise ValueError(f'Video ist nur {duration:.2f} Sekunden lang.')
            output=reserve(source.with_name(source.stem+'_Clip.mp4'),'.mp4',folder);created.append(output)
            crf={'Hohe Qualität':18,'Ausgewogen':23,'Kleine Datei':28}.get(options.get('video_profile'),23)
            height=int(options.get('video_height',0));scale=(f'scale=-2:min({height}\\,ih),' if height else '')
            args=[backend('ffmpeg'),'-hide_banner','-loglevel','error','-nostdin','-y','-protocol_whitelist','file,pipe','-ss',str(start),'-i',str(source),'-t',str(end-start),'-map','0:V:0','-map','0:a:0?','-c:v','libx264','-pix_fmt','yuv420p','-vf',scale+'pad=ceil(iw/2)*2:ceil(ih/2)*2','-crf',str(crf),'-c:a','aac','-movflags','+faststart',str(output)]
            result=run(args,timeout=7200,duration=end-start)
            if result.returncode or not output.stat().st_size:raise ValueError(result.stderr[-1000:] or 'Video konnte nicht gekürzt werden.')
            checkpoint(100,'Clip fertig')
        else:raise ValueError('Unbekanntes Werkzeug.')
        return [str(path) for path in created]
    except Exception:
        # These paths were reserved exclusively by this operation. Never delete
        # pre-existing user outputs or the originals.
        for path in created:path.unlink(missing_ok=True)
        raise
