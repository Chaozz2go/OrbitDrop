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
            from image_upscale import export_upscale
            [enlarged]=export_upscale(source,{'factor':2,'method':'lanczos'})
            with Image.open(enlarged) as check:results['upscale']=check.size==(320,200)
            from archive_options import create_archive,extract_options
            archive=root/'aes.zip';create_archive([source],archive,password='smoke-test',verify=True)
            destination=root/'extracted';destination.mkdir();[folder]=extract_options(archive,destination,password='smoke-test')
            results['archive_aes']=(Path(folder)/source.name).read_bytes()==source.read_bytes()
            from photo_metadata import metadata_plan
            from batch_rename import rename_with_journal,undo_journal
            plans,_=metadata_plan([source],'Renamed_{n}');renamed,journal=rename_with_journal(plans,root/'state');undo_journal(journal)
            results['rename_undo']=source.exists() and not Path(renamed[0]).exists()
            from device_test_ui import DeviceTestDialog
            tester=DeviceTestDialog();tester.show();QApplication.processEvents();results['device_dialog']=tester.isVisible() and tester.camera is None and tester.audio is None;tester.close()
            from upscale_ui import UpscaleDialog
            upscale=UpscaleDialog(source,lambda *args:None);upscale.show();deadline=time.monotonic()+15
            while not upscale.save_button.isEnabled() and time.monotonic()<deadline:QApplication.processEvents();time.sleep(.01)
            results['upscale_dialog']=upscale.save_button.isEnabled();upscale.close()
            from data_formats import parse,serialize
            from data_editor_ui import DataEditor
            broken=root/'broken.json';broken.write_text('{"server":"local"\n"port":80}',encoding='utf-8')
            data_editor=DataEditor(broken,'JSON');data_editor.show();deadline=time.monotonic()+10
            while data_editor.issue is None and time.monotonic()<deadline:QApplication.processEvents();time.sleep(.01)
            results['data_editor']=data_editor.issue is not None and data_editor.fix.isEnabled();data_editor.close()
            config=root/'config.json';config.write_text('{"name":"OrbitDrop","value":1.234567890123456789}',encoding='utf-8')
            yaml=convert(config,'YAML');toml=convert(yaml,'TOML')
            results['data_formats']=parse(toml.read_text(encoding='utf-8'),'TOML')==parse(config.read_text(encoding='utf-8'),'JSON')
            from admin_tools import certificate_report,certificate_bytes,file_hashes,log_lines
            from admin_tools_ui import AdminToolsDialog
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives.serialization import Encoding
            from datetime import datetime,timedelta,timezone
            key=rsa.generate_private_key(65537,2048);subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'orbitdrop.local')]);now=datetime.now(timezone.utc)
            certificate=x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(1).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1)).sign(key,hashes.SHA256())
            certpath=root/'cert.pem';certpath.write_bytes(certificate.public_bytes(Encoding.PEM));results['certificates']='orbitdrop.local' in certificate_report(certpath) and bool(certificate_bytes(certpath,'DER'))
            admin=AdminToolsDialog([config],'hash');admin.show();QApplication.processEvents();results['admin_dialog']=admin.isVisible() and 'hash' in admin.pages;admin.close()
            results['hashes']='SHA-256:' in file_hashes([config])
            log=root/'app.log';log.write_text('INFO ready\nERROR test\n',encoding='utf-8');results['logs']=''.join(log_lines(log,needle='ERROR'))=='ERROR test\n'
            pdf=root/'source.pdf'
            with pymupdf.open() as doc:doc.new_page().insert_text((20,40),'OrbitDrop');doc.save(pdf)
            with pymupdf.open(pdf) as doc:results['pdf']='OrbitDrop' in doc[0].get_text()
            editor=ImageEditor(source,lambda *args:None);editor.show();deadline=time.monotonic()+15
            while editor.canvas.pixmap is None and time.monotonic()<deadline:QApplication.processEvents();time.sleep(.01)
            results['qt']=editor.canvas.pixmap is not None;editor.close()
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
