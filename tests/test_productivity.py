import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from PIL import Image
from PySide6.QtWidgets import QApplication
from task_runtime import TaskControl,Cancelled,run_process
from preferences import Preferences
from archives import create_zip
from converter import convert
from tools import tool_outputs,page_indices
from app_ui import SettingsDialog,TasksWindow
from single_instance import SingleInstance

class ProductivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.prefs=Preferences(self.root/'state')
    def test_settings_and_history_persist(self):
        values=dict(self.prefs.values,image_quality=55,convert_key='Alt',files_key='Strg',output_dir=str(self.root))
        self.prefs.update(values)
        self.assertEqual(Preferences(self.root/'state').values,values)
        with self.assertRaises(ValueError):self.prefs.update(dict(values,files_key='Alt'))
        self.assertEqual(Preferences(self.root/'state').values,values)
        for index in range(53):self.prefs.record(str(index),[],[],'Fertig')
        self.assertEqual(len(Preferences(self.root/'state').history),50)
        self.prefs.clear_history();self.assertEqual(Preferences(self.root/'state').history,[])
    def test_zip_cancellation_cleans_partial_and_preserves_original(self):
        source=self.root/'source.bin';source.write_bytes(os.urandom(2*1024*1024));before=source.read_bytes()
        target=self.root/'output.zip'
        control=TaskControl()
        control.callback=lambda percent,message:control.cancel() if message.startswith('ZIP:') else None
        with control.activate():
            with self.assertRaises(Cancelled):create_zip([source],target)
        self.assertFalse(target.exists());self.assertEqual(source.read_bytes(),before)
    def test_subprocess_can_be_cancelled(self):
        control=TaskControl();timer=threading.Timer(.2,control.cancel);timer.start();start=time.monotonic()
        try:
            with control.activate():
                with self.assertRaises(Cancelled):run_process([sys.executable,'-c','import time;time.sleep(30)'],timeout=40)
        finally:timer.cancel()
        self.assertLess(time.monotonic()-start,5)
    def test_image_options_and_tools(self):
        source=self.root/'photo.png';Image.frombytes('RGB',(200,100),os.urandom(60000)).save(source);before=source.read_bytes()
        folder=self.root/'out';folder.mkdir()
        low=convert(source,'JPG',{'output_dir':str(folder),'image_quality':20})
        high=convert(source,'JPG',{'output_dir':str(folder),'image_quality':95})
        self.assertEqual(low.parent,folder);self.assertLess(low.stat().st_size,high.stat().st_size)
        outputs=tool_outputs('Bildgröße ändern',[source],{'width':80,'height':80,'keep_ratio':True},{'output_dir':str(folder)})
        with Image.open(outputs[0]) as image:self.assertEqual(image.size,(80,40))
        outputs=tool_outputs('Bild drehen',[source],{'angle':90},{})
        with Image.open(outputs[0]) as image:self.assertEqual(image.size,(100,200))
        self.assertEqual(source.read_bytes(),before)
    def test_pdf_merge_order_split_and_invalid_pages(self):
        import pymupdf
        sources=[]
        for title in ('First','Second'):
            source=self.root/(title+'.pdf');doc=pymupdf.open();doc.new_page().insert_text((20,30),title);doc.save(source);doc.close();sources.append(source)
        result=tool_outputs('PDFs zusammenfügen',sources[::-1],{},{})[0]
        with pymupdf.open(result) as doc:
            self.assertEqual(len(doc),2);self.assertIn('Second',doc[0].get_text());self.assertIn('First',doc[1].get_text())
        pages=tool_outputs('PDF aufteilen',[result],{'pages':'2,1'},{})
        with pymupdf.open(pages[0]) as doc:self.assertIn('First',doc[0].get_text())
        self.assertEqual(page_indices('1-2,2',2),[0,1])
        with self.assertRaises(ValueError):page_indices('0,9',2)
    def test_conversion_cancel_keeps_finished_results(self):
        from orbitdrop import Conversion
        import orbitdrop
        sources=[]
        for index in range(2):
            path=self.root/f'image{index}.png';Image.new('RGB',(20,10),'blue').save(path);sources.append(path)
        job=Conversion(sources,'JPG');original=orbitdrop.convert
        def first_then_cancel(source,target,options):
            result=original(source,target,options);job.control.cancel();return result
        with patch('orbitdrop.convert',side_effect=first_then_cancel):job.run()
        self.assertTrue(job.was_cancelled);self.assertEqual(len(job.outputs),1);self.assertTrue(Path(job.outputs[0]).exists())
        self.assertTrue(all(path.exists() for path in sources))
    def test_task_window_and_single_instance(self):
        window=TasksWindow(self.prefs);self.addCleanup(window.close)
        job=SimpleNamespace(control=TaskControl())
        key=window.add(job,'Test');window.progress(key,40,'40 % verarbeitet');self.assertEqual(window.rows[key]['bar'].value(),40)
        window.cancel_selected();self.assertTrue(job.control.cancelled.is_set())
        window.finish(key,[],[],True);self.assertEqual(self.prefs.history[-1]['status'],'Abgebrochen')
        one=SingleInstance(self.root/'instance');two=SingleInstance(self.root/'instance')
        self.assertTrue(one.acquire());self.addCleanup(one.release);self.assertFalse(two.acquire())
        self.app.processEvents()
        dialog=SettingsDialog(self.prefs);self.addCleanup(dialog.close)
        self.assertEqual(dialog.quality.value(),92)
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_video_resize_and_clip(self):
        source=self.root/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=96x64:r=15','-t','2','-c:v','libx264',str(source)],check=True)
        converted=convert(source,'MP4',{'video_height':480,'video_profile':'Kleine Datei'})
        probe=subprocess.run(['ffprobe','-v','error','-show_streams','-of','json',str(converted)],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(probe.stdout)['streams'][0]['height'],64)
        clip=tool_outputs('Video kürzen',[source],{'start':.5,'end':1.2},{})[0]
        probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(clip)],capture_output=True,text=True,check=True)
        self.assertAlmostEqual(float(json.loads(probe.stdout)['format']['duration']),.7,delta=.15)

if __name__=='__main__':unittest.main()
