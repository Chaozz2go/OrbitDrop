import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image
from PySide6.QtCore import Qt,QPointF,QMimeData,QUrl
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from edit_models import CutModel,read_frame
from image_editor import ImageEditor
from tools import tool_outputs
from circle_menu import home_actions
from orbitdrop import Wheel

class EditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def wait(self,condition,timeout=10):
        end=time.monotonic()+timeout
        while not condition() and time.monotonic()<end:self.app.processEvents();time.sleep(.01)
        self.assertTrue(condition())
    def video(self):
        path=self.root/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=96x64:r=10','-t','3','-c:v','libx264',str(path)],check=True)
        return path
    def test_cut_model_split_exclude_and_delete(self):
        model=CutModel(10);self.assertFalse(model.add(0));self.assertTrue(model.add(2));self.assertTrue(model.add(7));self.assertFalse(model.add(7))
        model.keep(1,False);self.assertEqual(model.ranges(),[(0,2),(7,10)])
        model.remove(0);self.assertEqual(model.cuts,[7]);self.assertEqual(model.ranges(),[(0,7),(7,10)])
    def test_crop_mouse_rotation_and_export_pixels(self):
        path=self.root/'source.png';image=Image.new('RGB',(200,100),'red')
        for x in range(100,200):
            for y in range(100):image.putpixel((x,y),(0,0,255))
        image.save(path);before=path.read_bytes();calls=[]
        editor=ImageEditor(path,lambda *args:calls.append(args));self.addCleanup(editor.close);editor.show();self.app.processEvents()
        rect=editor.canvas.image_rect()
        left=QPointF(rect.left(),rect.top()).toPoint()+QPointF(2,2).toPoint()
        right=QPointF(rect.center().x(),rect.bottom()-2).toPoint()
        QTest.mousePress(editor.canvas,Qt.MouseButton.LeftButton,pos=left);QTest.mouseMove(editor.canvas,right,10);QTest.mouseRelease(editor.canvas,Qt.MouseButton.LeftButton,pos=right)
        box=editor.canvas.crop_box();self.assertIsNotNone(box);self.assertLessEqual(box[2],101)
        editor.save();action,files,params=calls[0];result=tool_outputs(action,files,params,{})[0]
        with Image.open(result) as output:
            self.assertLessEqual(output.width,101);self.assertEqual(output.getpixel((10,10))[:3],(255,0,0))
        self.assertEqual(path.read_bytes(),before)
        rotated=tool_outputs('Bild bearbeiten',[path],{'angle':90,'crop':(0,0,50,100)},{})[0]
        with Image.open(rotated) as output:self.assertEqual(output.size,(50,100))
    def test_circle_first_action_then_click_format_without_redrag(self):
        path=self.root/'image.png';Image.new('RGB',(30,20),'red').save(path);calls=[]
        class Target:
            def convert_files(self,files,target):calls.append((files,target))
        wheel=Wheel(Target());self.addCleanup(wheel.close);wheel.open(automatic=True);self.app.processEvents()
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(path))])
        event=QDragEnterEvent(QPointF(190,190).toPoint(),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        wheel.dragEnterEvent(event);self.wait(lambda:not wheel.checking)
        self.assertEqual(wheel.labels,['KONVERTIEREN','BEARBEITEN','TOOLS'])
        drop=QDropEvent(QPointF(252,82),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        wheel.dropEvent(drop);self.app.processEvents();self.assertTrue(drop.isAccepted());self.assertTrue(wheel.latched);self.assertFalse(wheel.automatic)
        self.assertIn('format:PNG',wheel.labels)
        from direct_wheel import geometry
        point=next(entry[2] for entry in geometry(wheel) if entry[0]=='format:PNG')
        QTest.mouseClick(wheel,Qt.MouseButton.LeftButton,pos=point.toPoint());self.assertEqual(calls,[]);self.app.processEvents()
        self.assertEqual([([Path(p) for p in paths],action) for paths,action in calls],[([path],'PNG')])
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_frame_steps_follow_variable_timestamps(self):
        paths=[]
        for index in range(5):
            path=self.root/f'frame{index}.png';Image.new('RGB',(64,48),(index*40,40,100)).save(path);paths.append(path)
        manifest=self.root/'frames.txt'
        text=''
        for path,duration in zip(paths,[.04,.16,.08,.24,.2]):text+=f"file '{path.name}'\nduration {duration}\n"
        text+=f"file '{paths[-1].name}'\n";manifest.write_text(text)
        video=self.root/'variable.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','concat','-safe','1','-i',str(manifest),'-fps_mode','vfr','-c:v','libx264',str(video)],check=True)
        result=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','frame=best_effort_timestamp_time','-of','json',str(video)],capture_output=True,text=True,check=True)
        times=[float(frame['best_effort_timestamp_time']) for frame in json.loads(result.stdout)['frames']]
        self.assertGreater(len(set(round(times[i+1]-times[i],3) for i in range(len(times)-1))),1)
        for index,position in enumerate(times):
            if index+1<len(times):self.assertAlmostEqual(read_frame(video,position,1)[1],times[index+1],places=5)
            if index:self.assertAlmostEqual(read_frame(video,position,-1)[1],times[index-1],places=5)
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_multiple_cuts_export_and_rotate(self):
        video=self.video();before=hashlib.sha256(video.read_bytes()).hexdigest()
        outputs=tool_outputs('Video bearbeiten',[video],{'ranges':[(0,.5),(1.5,2.5)],'angle':90},{})
        result=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',outputs[0]],capture_output=True,text=True,check=True)
        info=json.loads(result.stdout);self.assertEqual((info['streams'][0]['width'],info['streams'][0]['height']),(64,96));self.assertAlmostEqual(float(info['format']['duration']),1.5,delta=.2)
        separate=tool_outputs('Video bearbeiten',[video],{'ranges':[(0,.5),(1,1.5)],'separate':True},{})
        self.assertEqual(len(separate),2);self.assertTrue(all(Path(path).is_file() for path in separate));self.assertEqual(hashlib.sha256(video.read_bytes()).hexdigest(),before)
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg missing')
    def test_editor_shortcuts_real_frame_and_cut_deletion(self):
        from video_editor import VideoEditor
        video=self.video();editor=VideoEditor(video,lambda *args:None);self.addCleanup(editor.reject);editor.show();editor.activateWindow();self.wait(lambda:editor.model is not None)
        QTest.keyClick(editor,Qt.Key.Key_Right);self.wait(lambda:editor.frame_job is None);self.assertAlmostEqual(editor.position,.1,places=5)
        QTest.keyClick(editor,Qt.Key.Key_C);self.assertEqual(len(editor.model.cuts),1)
        editor.select_segment(1);QTest.keyClick(editor,Qt.Key.Key_Delete);self.assertEqual(len(editor.model.cuts),1);self.assertFalse(editor.model.segments[1][2])
        editor.set_selected_keep(True);editor.marks.setCurrentRow(0);QTest.keyClick(editor,Qt.Key.Key_Delete,Qt.KeyboardModifier.ShiftModifier);self.assertEqual(editor.model.cuts,[])
        QTest.keyClick(editor,Qt.Key.Key_Left);self.wait(lambda:editor.frame_job is None);self.assertAlmostEqual(editor.position,0,places=5)
        with patch.object(editor.player,'play') as play:
            QTest.keyClick(editor,Qt.Key.Key_Space);play.assert_called_once()

if __name__=='__main__':unittest.main()
