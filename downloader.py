"""Isolated yt-dlp worker: cancel kills downloads and FFmpeg, private staging keeps partials out of outputs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import shutil
from link_selection import media_link
from filetypes import backend
from task_runtime import checkpoint,stop_process,copy_stream
from converter import reserve


def worker_command(config):
    if getattr(sys,'frozen',False):return [sys.executable,'--download-worker',str(config)]
    return [sys.executable,str(Path(__file__).with_name('orbitdrop.py')),'--download-worker',str(config)]


def invoke_worker(config):
    with tempfile.TemporaryDirectory(prefix='orbit-download-') as directory:
        directory=Path(directory);request=directory/'request.json';result=directory/'result.json';progress=directory/'progress.json'
        request.write_text(json.dumps({**config,'result':str(result),'progress':str(progress)}),encoding='utf-8')
        flags={'creationflags':subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform=='win32' else {'start_new_session':True}
        process=subprocess.Popen(worker_command(request),stdout=subprocess.PIPE,stderr=subprocess.PIPE,**flags)
        start=time.monotonic()
        try:
            while True:
                checkpoint()
                if time.monotonic()-start>(120 if config['operation']=='inspect' else 21600):raise TimeoutError('Zeitlimit beim Abrufen des Links erreicht.')
                try:
                    state=json.loads(progress.read_text(encoding='utf-8'));checkpoint(state.get('percent'),state.get('message','Download …'))
                except (OSError,ValueError):pass
                try:stdout,stderr=process.communicate(timeout=.12);break
                except subprocess.TimeoutExpired:pass
            checkpoint()
            if not result.exists():raise ValueError('Downloader konnte nicht starten: '+stderr.decode(errors='replace')[-700:])
            data=json.loads(result.read_text(encoding='utf-8'))
            if data.get('error'):raise ValueError(data['error'])
            if process.returncode:raise ValueError('Download fehlgeschlagen.')
            return data
        except BaseException:
            stop_process(process);raise


def inspect_link(url):
    if not media_link(url):raise ValueError('Bitte einen vollständigen http(s)-Link wählen.')
    return invoke_worker({'operation':'inspect','url':url})


def download_link(url,mode,folder,height=0):
    if not media_link(url) or mode not in ('audio','video'):raise ValueError('Ungültiger Downloadauftrag.')
    folder=Path(folder).resolve()
    if not folder.is_dir():raise ValueError('Zielordner existiert nicht.')
    if not backend('ffmpeg') or not backend('ffprobe'):raise ValueError('Bitte unter Tools → Konverter FFmpeg/FFprobe einrichten.')
    output=None
    try:
        with tempfile.TemporaryDirectory(prefix='orbit-media-') as staging:
            data=invoke_worker({'operation':'download','url':url,'mode':mode,'height':int(height),'staging':staging})
            source=Path(data['output']).resolve()
            if source.parent!=Path(staging).resolve() or not source.is_file():raise ValueError('Downloader meldete keine gültige Ergebnisdatei.')
            safe=''.join(c if c.isalnum() or c in ' -_.' else '_' for c in data.get('title','Download'))[:100].strip(' .') or 'Download'
            output=reserve(Path(safe),source.suffix,folder)
            checkpoint(96,'Download wird gespeichert …')
            with source.open('rb') as src,output.open('wb') as dst:copy_stream(src,dst)
            checkpoint(100,'Download fertig')
        return [str(output)]
    except BaseException:
        if output:output.unlink(missing_ok=True)
        raise


def worker_main(config_path):
    config=json.loads(Path(config_path).read_text(encoding='utf-8'));result=Path(config['result']);progress=Path(config['progress'])
    def report(percent,message):
        temp=progress.with_suffix('.tmp');temp.write_text(json.dumps({'percent':percent,'message':message}),encoding='utf-8');os.replace(temp,progress)
    class Logger:
        def debug(self,message):pass
        def warning(self,message):report(None,'Hinweis: '+str(message)[-250:])
        def error(self,message):pass
    def hook(state):
        total=state.get('total_bytes') or state.get('total_bytes_estimate')
        percent=min(90,state.get('downloaded_bytes',0)*90/total) if total else None
        speed=state.get('speed');eta=state.get('eta');message='Wird heruntergeladen'
        if speed:message+=f' · {speed/1024/1024:.1f} MB/s'
        if eta is not None:message+=f' · ca. {eta}s'
        report(percent,message)
    try:
        import yt_dlp
        runtimes={}
        for name,exe in [('deno','deno'),('node','node'),('quickjs','qjs')]:
            path=backend(exe)
            if path:runtimes[name]={'path':path}
        options={'quiet':True,'no_warnings':True,'logger':Logger(),'noplaylist':True,'socket_timeout':20,'retries':2,'fragment_retries':2,'js_runtimes':runtimes,'remote_components':set(),'cachedir':False}
        if backend('ffmpeg'):options['ffmpeg_location']=str(Path(backend('ffmpeg')).parent)
        if config['operation']=='inspect':
            with yt_dlp.YoutubeDL(options) as dl:info=dl.extract_info(config['url'],download=False)
            if not info or info.get('_type') in ('playlist','multi_video'):raise ValueError('Bitte einen einzelnen Audio-/Video-Link wählen; keine Playlist.')
            formats=info.get('formats') or [info]
            heights=sorted({int(f['height']) for f in formats if f.get('vcodec') not in (None,'none') and f.get('height')},reverse=True)
            data={'title':info.get('title','Download'),'duration':info.get('duration'),'heights':heights,'audio':any(f.get('acodec')!='none' for f in formats),'video':any(f.get('vcodec')!='none' and (f.get('height') or f.get('ext') in ('mp4','webm','mkv','mov','m4v','avi','flv','ogv','ts')) for f in formats)}
        else:
            staging=Path(config['staging']);audio=config['mode']=='audio';height=config.get('height',0)
            limit=f'[height<={height}]' if height else ''
            options.update({'outtmpl':str(staging/'media.%(ext)s'),'progress_hooks':[hook],'postprocessor_hooks':[lambda s:report(92,'Audio/Video wird verarbeitet …')],'overwrites':False,'format':'bestaudio/best' if audio else f'bestvideo{limit}+bestaudio/best{limit}','postprocessors':[{'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':'192'}] if audio else [],'merge_output_format':'mkv'})
            with yt_dlp.YoutubeDL(options) as dl:info=dl.extract_info(config['url'],download=True)
            outputs=[p for p in staging.iterdir() if p.is_file() and p.suffix.lower() in ('.mp3','.mp4','.webm','.mkv','.mov','.m4v','.avi','.flv','.ogv','.ts')]
            if len(outputs)!=1:raise ValueError('Download lieferte kein eindeutiges Audio-/Video-Ergebnis.')
            data={'output':str(outputs[0]),'title':info.get('title','Download')}
        result.write_text(json.dumps(data),encoding='utf-8');return 0
    except Exception as error:
        result.write_text(json.dumps({'error':str(error)[-1800:]}),encoding='utf-8');return 1
