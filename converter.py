from pathlib import Path
import json
from task_runtime import checkpoint
from PIL import Image
from filetypes import inspect_file, backend, run
from extended import IMAGE_TYPES, convert_picture, pdf_convert, office_convert, subtitle_convert, archive_convert

EXTENSIONS = {'JSON':'.json','YAML':'.yaml','TOML':'.toml','XML':'.xml','JSONL':'.jsonl','PEM':'.pem','DER':'.der','SVG':'.svg',**IMAGE_TYPES, 'MP4': '.mp4', 'MOV': '.mov', 'MKV': '.mkv', 'WEBM': '.webm', 'AVI': '.avi', 'WMV': '.wmv', 'GIF': '.gif',
              'MP3': '.mp3', 'M4A': '.m4a', 'WAV': '.wav', 'FLAC': '.flac', 'OGG': '.ogg', 'OPUS': '.opus', 'AIFF': '.aiff', 'WMA': '.wma',
              'STANDBILD': '.png', 'TXT': '.txt', 'DOCX': '.docx', 'PPTX': '.pptx', 'XLSX': '.xlsx', 'ODS': '.ods', 'CSV': '.csv', 'TSV': '.tsv',
              'MD': '.md', 'EPUB': '.epub', 'HTML': '.html', 'SRT': '.srt', 'VTT': '.vtt', 'ZIP': '.zip', 'TAR': '.tar', 'GZIP': '.tar.gz'}

def reserve(source, extension, output_dir=None):
    folder=Path(output_dir) if output_dir else source.parent
    if not folder.is_dir():raise ValueError("Ausgabeordner existiert nicht.")
    index = 0
    while True:
        suffix = '' if index == 0 else f'_{index}'
        output = folder/f'{source.stem}_converted{suffix}{extension}'
        try:
            with output.open('xb'):
                pass
            return output
        except FileExistsError:
            index += 1

def convert(source, target, options=None):
    options=options or {}
    checkpoint(0,"Datei wird geprüft …")
    source = Path(source).resolve()
    info = inspect_file(source)
    if target not in info.actions:
        raise ValueError(info.message or 'Aktion passt nicht zum Dateiinhalt.')
    extension = EXTENSIONS[target]
    if info.kind in ('PDF','PPT','PPTX') and target in ('PNG','JPG'):
        extension = '.' + target.lower() + '.zip'
    output = reserve(source, extension, options.get("output_dir"))
    try:
        if info.kind=='Zertifikat':
            from admin_tools import certificate_bytes
            output.write_bytes(certificate_bytes(source,target))
        elif info.kind in ('JSON','YAML','TOML','XML','JSONL') or info.kind in ('CSV','TSV') and target in ('JSON','YAML','TOML','XML','JSONL','CSV','TSV'):
            from data_formats import convert_data
            convert_data(source,target,output)
        elif target=='SVG' and info.kind=='Bild':
            from image_processing import process_image
            process_image(source,'SVG',options.get('processing',{}),output)
        elif info.kind in ('Bild','SVG'):
            convert_picture(source,target,output,svg=info.kind=='SVG',quality=int(options.get('image_quality',92)))
        elif info.kind == 'PDF':
            pdf_convert(source,target,output)
        elif info.kind in ('SRT','VTT'):
            subtitle_convert(source,target,output)
        elif info.kind in ('ZIP','TAR','GZIP','RAR'):
            archive_convert(source,target,info.kind,output)
        elif info.kind not in ('Video','Audio'):
            office_convert(source,target,info.kind,output)
        else:
            duration=None
            if target!='STANDBILD':
                probe=run([backend('ffprobe'),'-v','error','-protocol_whitelist','file,pipe','-show_entries','format=duration','-of','json',str(source)],timeout=30)
                if probe.returncode==0:
                    try:duration=float(json.loads(probe.stdout)['format']['duration'])
                    except (KeyError,ValueError):pass
            profile=options.get('video_profile','Ausgewogen')
            crf={'Hohe Qualität':18,'Ausgewogen':23,'Kleine Datei':28}.get(profile,23)
            height=int(options.get('video_height',0))
            scale=(f'scale=-2:min({height}\\,ih),' if height else '')
            args = [backend('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                    '-protocol_whitelist', 'file,pipe', '-i', str(source)]
            if target in ('MP4','MOV','MKV'):
                args += ['-map', '0:V:0', '-map', '0:a:0?', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                         '-vf', scale+'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-crf', str(crf), '-c:a', 'aac']
                if target in ('MP4','MOV'):
                    args += ['-movflags', '+faststart']
            elif target == 'WEBM':
                args += ['-map', '0:V:0', '-map', '0:a:0?', '-c:v', 'libvpx-vp9', '-crf', str(crf+9), '-b:v', '0', '-c:a', 'libopus']
                if height:args+=['-vf',f'scale=-2:min({height}\\,ih)']
            elif target in ('AVI','WMV'):
                args += ['-map','0:V:0','-map','0:a:0?', '-c:v', 'mpeg4' if target=='AVI' else 'wmv2', '-q:v','4', '-c:a','libmp3lame' if target=='AVI' else 'wmav2']
            elif target == 'GIF':
                args += ['-map','0:V:0','-an','-vf','fps=12,scale=480:-1:flags=lanczos','-loop','0']
            elif target == 'STANDBILD':
                args += ['-map', '0:V:0', '-frames:v', '1', '-an', '-c:v', 'png', '-update', '1']
            else:
                args += ['-map', '0:a:0', '-vn', '-c:a', {'MP3':'libmp3lame', 'M4A':'aac', 'WAV':'pcm_s16le', 'FLAC':'flac', 'OGG':'libvorbis', 'OPUS':'libopus', 'AIFF':'pcm_s16be', 'WMA':'wmav2'}[target]]
            result = run(args + [str(output)], timeout=7200, duration=duration)
            if result.returncode:
                raise ValueError(result.stderr[-1200:] or 'Medienkonvertierung fehlgeschlagen.')
            if not output.stat().st_size:
                raise ValueError('Keine Ausgabe erzeugt.')
        checkpoint(100,"Datei fertig")
        return output
    except Exception:
        output.unlink(missing_ok=True)
        raise
