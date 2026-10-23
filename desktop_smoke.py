"""Exercise bundled native libraries and real media without writing user data."""
import importlib.util,json,tempfile,time
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
        with tempfile.TemporaryDirectory(prefix='orbit-smoke-') as temporary:
            root=Path(temporary)
            from orbitdrop import Controller
            from preferences import Preferences
            from dashboard_ui import Dashboard
            from types import SimpleNamespace
            prefs=Preferences(root/'prefs')
            c=SimpleNamespace(prefs=prefs,setup_job=None,backend_check=None,backend_status=[])
            for name in ('cancel_setup','check_backends','setup_tool','refresh_settings','install_update','updates','show_tasks','circle_action','download_dialog','tools','pause_shortcuts'):setattr(c,name,lambda *args:None)
            dashboard=Dashboard(c);dashboard.show();QApplication.processEvents()
            results['dashboard']=dashboard.isVisible() and QApplication.activeModalWidget() is None
            dashboard.open_page(3);results['dashboard_settings']=dashboard.settings_panel.isVisible()
            dashboard.open_page('Updates');results['dashboard_updates']=dashboard.updates_panel.isVisible() and dashboard.updates_panel.job is None;dashboard.close()
            from download_manager import DownloadManager
            manager=DownloadManager(c);manager.show();QApplication.processEvents();results['download_manager']=manager.isVisible() and manager.composer is not None;manager.close()
            source=root/'image.png';Image.new('RGB',(160,100),'#447788').save(source)
            image=convert(source,'WEBP');results['image']=image.stat().st_size>0
            pdf=root/'source.pdf'
            with pymupdf.open() as doc:doc.new_page().insert_text((20,40),'OrbitDrop');doc.save(pdf)
            with pymupdf.open(pdf) as doc:results['pdf']='OrbitDrop' in doc[0].get_text()
            editor=ImageEditor(source,lambda *args:None);editor.show();QApplication.processEvents();results['qt']=editor.canvas.pixmap is not None;editor.close()
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
