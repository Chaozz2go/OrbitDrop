import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from array import array
import math,threading,tempfile,time,unittest,wave,shutil,subprocess
from pathlib import Path
from PySide6.QtCore import Qt,QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from waveform import extract_waveform,WaveformCancelled
from audio_editor import AudioEditor
from video_editor import VideoEditor

class WaveformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.audio=self.root/'stereo.wav';samples=array('h');rate=16000
        for i in range(rate*3):
            value=0 if i<rate else int((.7 if i<2*rate else .15)*32767*math.sin(2*math.pi*440*i/rate));samples.extend((value,-value))
        with wave.open(str(self.audio),'wb') as output:output.setnchannels(2);output.setsampwidth(2);output.setframerate(rate);output.writeframes(samples.tobytes())
    def wait(self,condition):
        end=time.monotonic()+12
        while not condition() and time.monotonic()<end:self.app.processEvents();time.sleep(.01)
        self.assertTrue(condition())
    def test_stereo_antiphase_and_silence_are_visible(self):
        progress=[];result=extract_waveform(self.audio,points=300,progress=progress.append);self.assertEqual(result['channels'],2);self.assertAlmostEqual(result['duration'],3,places=2)
        for peaks in result['peaks']:
            self.assertLess(max(peaks[:90]),.01);self.assertGreater(max(peaks[110:190]),.6);self.assertLess(max(peaks[220:280]),.2)
        self.assertEqual(len(result['peaks'][0]),300);self.assertTrue(progress)
        stop=threading.Event();stop.set()
        with self.assertRaises(WaveformCancelled):extract_waveform(self.audio,stopped=stop)
    def test_audio_waveform_select_delete_restore_and_marker_removal(self):
        calls=[];editor=AudioEditor(self.audio,lambda *args:calls.append(args));self.addCleanup(editor.reject);editor.show();editor.activateWindow();self.wait(lambda:editor.model is not None and bool(editor.waveform.peaks));editor.model.add(1);editor.model.add(2);editor.refresh_lists();self.app.processEvents()
        point=QPointF(editor.waveform.width()/2,editor.waveform.height()/2).toPoint();QTest.mouseClick(editor.waveform,Qt.MouseButton.LeftButton,pos=point);QTest.keyClick(editor.waveform,Qt.Key.Key_Delete)
        self.assertEqual(editor.model.cuts,[1,2]);self.assertFalse(editor.model.segments[1][2]);self.assertEqual(editor.kept_position(1.5),2)
        editor.set_selected_keep(True);self.assertTrue(editor.model.segments[1][2]);editor.marks.setCurrentRow(0);QTest.keyClick(editor,Qt.Key.Key_Delete,Qt.KeyboardModifier.ShiftModifier);self.assertEqual(editor.model.cuts,[2])
        editor.save();self.assertEqual(calls[0][0],'Audio bearbeiten');self.assertTrue(editor.stopped.is_set())
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg missing')
    def test_video_waveform_is_time_aligned_and_delete_keeps_cuts(self):
        path=self.root/'source.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=128x96:r=10:d=3','-i',str(self.audio),'-c:v','libx264','-c:a','aac','-shortest',str(path)],check=True)
        editor=VideoEditor(path,lambda *args:None);self.addCleanup(editor.reject);editor.show();editor.activateWindow();self.wait(lambda:editor.model is not None and bool(editor.waveform.peaks));editor.model.add(1);editor.model.add(2);editor.refresh_lists();editor.select_segment(1);QTest.keyClick(editor,Qt.Key.Key_Delete)
        self.assertFalse(editor.model.segments[1][2]);self.assertEqual(editor.model.cuts,[1,2]);self.assertEqual(editor.waveform.selected_segment,1);self.assertEqual(editor.timeline.selected_segment,1)
        editor.seek(2);self.wait(lambda:editor.frame_job is None);self.assertAlmostEqual(editor.waveform.position,editor.position/editor.model.duration,places=4)
        editor.reject();self.assertTrue(editor.waveform.closed)
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg missing')
    def test_video_without_audio_returns_no_fake_waveform(self):
        path=self.root/'silent.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=64x48:r=5:d=1','-c:v','libx264',str(path)],check=True)
        result=extract_waveform(path,duration=1);self.assertEqual(result['channels'],0);self.assertEqual(result['peaks'],[])

if __name__=='__main__':unittest.main()
