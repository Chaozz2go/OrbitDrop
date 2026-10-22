import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QPointF,QMimeData,QUrl,Qt
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from orbitdrop import Wheel
from circle_menu import action_color,edit_actions
from link_selection import media_link
from task_runtime import TaskControl,Cancelled
from downloader import download_link,invoke_worker,worker_main

class MenuDownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def test_contextual_actions_are_direct_and_grouped(self):
        from circle_menu import direct_actions,direct_color
        labels=direct_actions(['image.png'],'Bild',['PNG','JPG','SVG'])
        self.assertIn('format:PNG',labels);self.assertIn('format:SVG ERWEITERT',labels);self.assertIn('edit:ZUSCHNEIDEN',labels);self.assertIn('tool:TERMINAL',labels);self.assertFalse(any(key.startswith('app:') for key in labels));self.assertNotIn('tool:EXPLORER',labels)
        self.assertEqual(len({direct_color(label) for label in labels}),3)
        self.assertNotIn('DREHEN',labels);self.assertIn('edit:90° LINKS',labels)
        self.assertIn('SCHNEIDEN',edit_actions(['sound.mp3'],'Audio'))
    def test_link_validation_and_drag(self):
        for bad in ['file:///tmp/a','javascript:alert(1)','https://user:secret@host/a','https://x/a\nhttps://y','not a link','https://x:bad/a']:self.assertIsNone(media_link(bad))
        self.assertEqual(media_link(' https://example.org/watch?v=1 '),'https://example.org/watch?v=1')
        calls=[]
        class Target:
            def download_dialog(self,url,mode):calls.append((url,mode))
        wheel=Wheel(Target());self.addCleanup(wheel.close);wheel.open();mime=QMimeData();mime.setUrls([QUrl('https://example.org/video')])
        enter=QDragEnterEvent(QPointF(190,190).toPoint(),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier);wheel.dragEnterEvent(enter)
        self.app.processEvents();self.assertTrue(enter.isAccepted());self.assertIn('download:AUDIO LADEN',wheel.labels)
        from direct_wheel import geometry
        point=next(entry[2] for entry in geometry(wheel) if entry[0]=='download:AUDIO LADEN')
        drop=QDropEvent(point,Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier);wheel.dropEvent(drop);self.app.processEvents()
        self.assertEqual(calls,[('https://example.org/video','audio')])
    def test_download_output_collision_and_cancel_cleanup(self):
        existing=self.root/'Title_converted.mp3';existing.write_bytes(b'old')
        def fake(config):
            target=Path(config['staging'])/'media.mp3';target.write_bytes(b'media');return {'output':str(target),'title':'Title'}
        with patch('downloader.invoke_worker',side_effect=fake),patch('downloader.backend',return_value='/usr/bin/ffmpeg'):
            outputs=download_link('https://example.org/a','audio',self.root)
            self.assertEqual(Path(outputs[0]).read_bytes(),b'media');self.assertEqual(existing.read_bytes(),b'old')
            control=TaskControl();control.cancel()
            with control.activate(),self.assertRaises(Cancelled):download_link('https://example.org/a','audio',self.root)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),['Title_converted.mp3','Title_converted_1.mp3'])
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg missing')
    def test_actual_http_audio_and_video_download(self):
        import functools,http.server,threading
        from downloader import inspect_link
        source=self.root/'remote.mp4';folder=self.root/'downloads';folder.mkdir()
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=96x64:rate=10:duration=1','-f','lavfi','-i','sine=duration=1','-c:v','libx264','-c:a','aac','-shortest',str(source)],check=True)
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(self.root)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}/remote.mp4'
            info=inspect_link(url);self.assertTrue(info['audio']);self.assertTrue(info['video'])
            for mode in ('audio','video'):
                outputs=download_link(url,mode,folder);self.assertEqual(len(outputs),1);self.assertGreater(Path(outputs[0]).stat().st_size,100)
                result=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',outputs[0]],capture_output=True,text=True,check=True)
                kinds=[stream['codec_type'] for stream in json.loads(result.stdout)['streams']]
                self.assertIn('audio',kinds)
                if mode=='video':self.assertIn('video',kinds)
                else:self.assertNotIn('video',kinds)
        finally:server.shutdown();server.server_close();thread.join()

    def test_worker_process_cancellation(self):
        script=self.root/'sleep.py';script.write_text('import time\ntime.sleep(30)\n')
        control=TaskControl();import threading
        timer=threading.Timer(.2,control.cancel);timer.start()
        start=time.monotonic()
        with patch('downloader.worker_command',return_value=[sys.executable,str(script)]),control.activate(),self.assertRaises(Cancelled):invoke_worker({'operation':'inspect','url':'https://example.org'})
        timer.join();self.assertLess(time.monotonic()-start,3)
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg missing')
    def test_audio_cuts_and_filmstrip_select_remove_restore(self):
        from tools import tool_outputs
        from video_editor import VideoEditor
        audio=self.root/'sound.wav';video=self.root/'video.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=3',str(audio)],check=True)
        outputs=tool_outputs('Audio bearbeiten',[audio],{'ranges':[(0,.5),(2,3)]},{})
        result=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',outputs[0]],capture_output=True,text=True,check=True)
        self.assertAlmostEqual(float(json.loads(result.stdout)['format']['duration']),1.5,delta=.1)
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=10:duration=3','-c:v','libx264',str(video)],check=True)
        calls=[];editor=VideoEditor(video,lambda *args:calls.append(args));editor.show();self.app.processEvents();self.addCleanup(editor.close)
        deadline=time.monotonic()+10
        while (editor.model is None or editor.frame_job) and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        self.assertIsNotNone(editor.model);editor.model.add(1);editor.model.add(2);editor.refresh_lists()
        x=editor.timeline.x_for(1.5);QTest.mouseClick(editor.timeline,Qt.MouseButton.LeftButton,pos=QPointF(x,70).toPoint());self.assertEqual(editor.timeline.selected_segment,1)
        editor.remove_segment_button.click();self.assertEqual(editor.model.ranges(),[(0,1),(2,3)]);self.assertTrue(editor.restore_segment_button.isEnabled());self.assertEqual(editor.kept_position(1.5),2)
        editor.restore_segment_button.click();self.assertEqual(len(editor.model.ranges()),3)
        editor.remove_segment_button.click()
        while editor.frame_job and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        editor.save();self.assertEqual(calls[0][2]['ranges'],[(0,1),(2,3)])

if __name__=='__main__':unittest.main()
