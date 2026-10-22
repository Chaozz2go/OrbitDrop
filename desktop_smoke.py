"""Exercise bundled native libraries and real media without writing user data."""
import importlib.util,json,tempfile,time,sys
from pathlib import Path


def self_test(report):
    results={};ok=True
    try:
        from PIL import Image
        from converter import convert
        from filetypes import backend,run,inspect_file
        from edit_models import read_frame
        from waveform import extract_waveform
        import pymupdf
        from PySide6.QtWidgets import QApplication
        from image_editor import ImageEditor
        from orbitdrop import Wheel
        from octagon_menu import geometry,MORE
        from PySide6.QtCore import QPointF
        from types import SimpleNamespace
        from changelog import local_entries,resource_path
        from app_version import VERSION
        results['changelog']=any(entry['version']==VERSION for entry in local_entries())
        results['manual']=resource_path('docs/OrbitDrop-Handbuch.html').is_file()
        if sys.platform=='win32':
            from shortcut_events import ShortcutEvents
            from preferences import DEFAULTS
            listener=ShortcutEvents(DEFAULTS).start()
            try:results['shortcut_events']=listener.ready.wait(3) and listener.available and not listener.error
            finally:listener.close()
        with tempfile.TemporaryDirectory(prefix='orbit-smoke-') as temporary:
            root=Path(temporary);source=root/'image.png';Image.new('RGB',(160,100),'#447788').save(source)
            image=convert(source,'WEBP');results['image']=image.stat().st_size>0
            pdf=root/'source.pdf'
            with pymupdf.open() as doc:doc.new_page().insert_text((20,40),'OrbitDrop');doc.save(pdf)
            with pymupdf.open(pdf) as doc:results['pdf']='OrbitDrop' in doc[0].get_text()
            editor=ImageEditor(source,lambda *args:None);editor.show();QApplication.processEvents();results['qt']=editor.canvas.pixmap is not None;editor.close()
            wheel=Wheel(SimpleNamespace());wheel.open(mode='edit');wheel.files=[str(source)];wheel.kind='Bild';wheel.formats=['PNG'];wheel.display_mode()
            compact={key:(path.boundingRect().size(),point+QPointF(wheel.pos())) for key,path,point,_ in geometry(wheel)};wheel.select_action(MORE);QApplication.processEvents()
            expanded=geometry(wheel);results['octagon_menu']=wheel.menu_expanded and len(expanded)>len(compact) and all(abs(path.boundingRect().width()-wheel.tile_size)<1e-6 and (key not in compact or compact[key]==(path.boundingRect().size(),point+QPointF(wheel.pos()))) for key,path,point,_ in expanded);wheel.close()
            if not backend('ffmpeg') or not backend('ffprobe'):raise RuntimeError('FFmpeg/FFprobe fehlen im Windows-Paket.')
            video=root/'video.mp4';command=[backend('ffmpeg'),'-v','error','-f','lavfi','-i','color=c=blue:s=96x64:r=10:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-c:a','aac','-shortest',str(video)]
            result=run(command,timeout=30)
            if result.returncode:raise RuntimeError('FFmpeg-Test fehlgeschlagen: '+result.stderr[-500:])
            results['detection']=inspect_file(video).kind=='Video';results['frames']=read_frame(video,.2)[0].size==(96,64);results['waveform']=bool(extract_waveform(video)['peaks'])
            if importlib.util.find_spec('local_ocr'):
                from local_ocr import find_tessdata,recognize_text
                tess=find_tessdata('eng');results['ocr_data']=bool(tess)
                page=pymupdf.open();p=page.new_page(width=400,height=150);p.insert_text((20,80),'ORBITDROP 12345',fontsize=30);pix=p.get_pixmap(matrix=pymupdf.Matrix(2,2));scan=root/'scan.png';pix.save(scan);page.close()
                results['ocr']='12345' in recognize_text(scan,'eng',200,tess)
            if importlib.util.find_spec('audio_tools'):
                from audio_tools import improve_audio
                output=improve_audio([convert(video,'WAV')],{'normalize':True,'format':'FLAC'},{});results['audio']=Path(output[0]).stat().st_size>0
        ok=bool(results) and all(results.values())
    except Exception as error:ok=False;results['error']=str(error)
    Path(report).write_text(json.dumps({'ok':ok,'checks':results},ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if ok else 1
