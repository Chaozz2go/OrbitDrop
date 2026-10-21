import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import io,json,shutil,subprocess,tempfile,time,unittest
from pathlib import Path
from PIL import Image
from PySide6.QtCore import Qt,QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from annotations import render_marks
from annotation_ui import AnnotationDialog
from compression import image_bytes,compress_files,compression_settings
from compression_ui import CompressionDialog,QuickActionsDialog
from quick_actions import save_preset,validate_presets
from preferences import Preferences
from tools import tool_outputs
from orbitdrop import Wheel
from direct_wheel import geometry
from task_runtime import TaskControl,Cancelled

class ToolboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.source=self.root/'source.png';Image.effect_noise((320,200),80).convert('RGBA').save(self.source);self.prefs=Preferences(self.root/'prefs')
    def wait(self,condition):
        deadline=time.monotonic()+15
        while not condition() and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        self.assertTrue(condition())
    def test_image_limit_resize_alpha_and_original_preserved(self):
        before=self.source.read_bytes();data,quality,size=image_bytes(self.source,{'format':'WEBP','target_mb':.008,'max_edge':200});self.assertLessEqual(len(data),8000);self.assertEqual(size,(200,125));self.assertLessEqual(quality,82)
        output=tool_outputs('Komprimieren',[self.source],{'format':'WEBP','target_mb':.008,'max_edge':200},{})[0]
        self.assertEqual(self.source.read_bytes(),before);self.assertLessEqual(Path(output).stat().st_size,8000)
        alpha=self.root/'alpha.png';Image.new('RGBA',(50,50),(0,0,0,0)).save(alpha)
        with Image.open(io.BytesIO(image_bytes(alpha,{'format':'JPG'})[0])) as image:self.assertEqual(image.getpixel((20,20)),(255,255,255))
        with Image.open(io.BytesIO(image_bytes(alpha,{'format':'WEBP'})[0])) as image:self.assertEqual(image.getpixel((20,20))[3],0)
    def test_unreachable_target_cancel_and_invalid_settings_clean_outputs(self):
        before=set(self.root.iterdir())
        with self.assertRaises(ValueError):compress_files([self.source],{'format':'PNG','target_mb':.000001},{})
        self.assertEqual(set(self.root.iterdir()),before)
        control=TaskControl();control.cancel()
        with control.activate(),self.assertRaises(Cancelled):compress_files([self.source],{}, {})
        self.assertEqual(set(self.root.iterdir()),before)
        for params in ({'target_mb':float('nan')},{'max_edge':-1},{'quality':200}):
            with self.assertRaises(ValueError):compression_settings(params)
    def test_flat_redaction_has_no_original_pixels_or_metadata(self):
        source=self.root/'sensitive.png';image=Image.new('RGBA',(80,50),(255,0,0,70));image.save(source);before=source.read_bytes()
        marks=[dict(kind='redact',x1=10,y1=10,x2=40,y2=30)]
        output=tool_outputs('Bild markieren',[source],{'marks':marks},{})[0]
        with Image.open(output) as image:
            self.assertEqual(image.getpixel((20,20)),(0,0,0,255));self.assertEqual(image.getpixel((2,2)),(255,0,0,70));self.assertEqual(len(image.getexif()),0)
        self.assertEqual(source.read_bytes(),before)
    def test_all_annotations_render_and_validate_coordinates(self):
        image=Image.new('RGBA',(200,120),'white');marks=[dict(kind='arrow',x1=10,y1=20,x2=60,y2=20),dict(kind='rectangle',x1=70,y1=10,x2=100,y2=40),dict(kind='text',x1=10,y1=60,x2=150,y2=100,text='Hallo äö')]
        result=render_marks(image,marks);self.assertNotEqual(result.getpixel((30,20)),(255,255,255,255));self.assertNotEqual(result.getpixel((70,20)),(255,255,255,255));self.assertNotEqual(result.tobytes(),image.tobytes())
        with self.assertRaises(ValueError):render_marks(image,[dict(kind='redact',x1=-1,y1=0,x2=5,y2=5)])
    def test_annotation_mouse_undo_redo_and_export(self):
        calls=[];dialog=AnnotationDialog(self.source,lambda *args:calls.append(args));self.addCleanup(dialog.close);dialog.show();self.app.processEvents();rect=dialog.canvas.image_rect();start=QPointF(rect.left()+10,rect.top()+10).toPoint();end=QPointF(rect.center()).toPoint()
        QTest.mousePress(dialog.canvas,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(dialog.canvas,end,10);QTest.mouseRelease(dialog.canvas,Qt.MouseButton.LeftButton,pos=end)
        self.assertEqual(len(dialog.marks),1);dialog.undo_mark();self.assertFalse(dialog.marks);dialog.redo_mark();self.assertEqual(len(dialog.marks),1)
        dialog.save();self.assertEqual(calls[0][0],'Bild markieren');self.assertTrue(Path(tool_outputs(*calls[0],{})[0]).is_file())
    def test_presets_persist_filter_and_dispatch_with_readable_menu_names(self):
        save_preset(self.prefs,'Webbilder','Bild',{'max_edge':1600});save_preset(self.prefs,'Audio klein','Audio',{'audio_kbps':64})
        prefs=Preferences(self.prefs.root);self.assertEqual(len(prefs.values['quick_actions']),2)
        with self.assertRaises(ValueError):save_preset(prefs,'Webbilder','Bild',{})
        with self.assertRaises(ValueError):validate_presets([{}])
        calls=[]
        class Target:
            def __init__(self):self.prefs=prefs
            def circle_action(self,files,action,kind):calls.append((files,action,kind))
        wheel=Wheel(Target());self.addCleanup(wheel.close);wheel.open(mode='edit');wheel.files=[str(self.source)];wheel.kind='Bild';wheel.display_mode();self.app.processEvents()
        keys=[key for key in wheel.labels if key.startswith('edit:quick:')];self.assertEqual(len(keys),1);self.assertEqual(wheel.action_titles[keys[0]],'Webbilder');self.assertIn('edit:MARKIEREN',wheel.labels);self.assertIn('edit:KOMPRIMIEREN',wheel.labels)
        point=next(point for key,path,point,index in geometry(wheel) if key==keys[0]);QTest.mouseClick(wheel,Qt.MouseButton.LeftButton,pos=point.toPoint());self.app.processEvents();self.assertTrue(calls[0][1].startswith('quick:'))
        manager=QuickActionsDialog(prefs);self.addCleanup(manager.close);manager.starters();self.assertEqual(len(prefs.values['quick_actions']),4);manager.items.setCurrentRow(0);manager.remove();self.assertEqual(len(prefs.values['quick_actions']),3)
    def test_compression_preview_submit_and_save_recipe(self):
        calls=[];dialog=CompressionDialog([str(self.source)],'Bild',lambda *args:calls.append(args),self.prefs);self.addCleanup(dialog.close);dialog.show();self.wait(lambda:dialog.preview_image is not None and dialog.start.isEnabled())
        self.assertIsNotNone(dialog.original_image);dialog.preset_name.setText('Mein Webbild');dialog.save_recipe();self.assertEqual(self.prefs.values['quick_actions'][0]['name'],'Mein Webbild');dialog.apply();self.assertEqual(calls[0][0],'Komprimieren')
    def test_pdf_compression_preserves_text_and_rejects_impossible_limit(self):
        import pymupdf
        source=self.root/'source.pdf'
        with pymupdf.open() as pdf:pdf.new_page().insert_text((20,40),'OrbitDrop PDF');pdf.save(source)
        output=compress_files([source],{}, {})[0]
        with pymupdf.open(output) as pdf:self.assertIn('OrbitDrop PDF',pdf[0].get_text())
        before=set(self.root.iterdir())
        with self.assertRaises(ValueError):compress_files([source],{'target_mb':.000001},{})
        self.assertEqual(set(self.root.iterdir()),before)
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_video_two_pass_and_audio_limit(self):
        source=self.root/'source.mp4';audio=self.root/'audio.wav'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=256x144:rate=15:duration=2','-f','lavfi','-i','sine=duration=2','-c:v','libx264','-c:a','aac','-shortest',str(source)],check=True)
        video=Path(compress_files([source],{'target_mb':.1,'video_height':144},{})[0]);self.assertLessEqual(video.stat().st_size,100000)
        result=subprocess.run(['ffprobe','-v','error','-show_streams','-of','json',str(video)],capture_output=True,text=True,check=True);self.assertEqual({s['codec_type'] for s in json.loads(result.stdout)['streams']},{'audio','video'})
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=2',str(audio)],check=True)
        output=Path(compress_files([audio],{'target_mb':.04},{})[0]);self.assertLessEqual(output.stat().st_size,40000)

if __name__=='__main__':unittest.main()
