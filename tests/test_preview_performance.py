import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,threading,time,unittest,subprocess,shutil,wave
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from preview_runtime import PreviewCache,preview_cache,preview_pool,source_key
from image_editor import ImageEditor
from edit_models import FrameReader,read_frame
from filmstrip import ThumbnailJob
from waveform import WaveJob

class PreviewPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);preview_cache.clear()
    def wait(self,condition):
        end=time.monotonic()+10
        while not condition() and time.monotonic()<end:self.app.processEvents();time.sleep(.005)
        self.assertTrue(condition())
    def video(self):
        if not shutil.which('ffmpeg'):self.skipTest('FFmpeg missing')
        path=self.root/'video.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=128x96:r=10:d=3','-c:v','libx264',str(path)],check=True)
        return path
    def test_cache_budget_lru_and_changed_file_identity(self):
        cache=PreviewCache(10);cache.put('a','A',4);cache.put('b','B',4);cache.get('a');cache.put('c','C',4)
        self.assertIsNone(cache.get('b'));self.assertEqual(cache.get('a'),'A');self.assertLessEqual(cache.used,10)
        cache.put('a','too large',20);self.assertIsNone(cache.get('a'));self.assertLessEqual(cache.used,10)
        path=self.root/'file';path.write_bytes(b'old');old=source_key('preview',path);path.write_bytes(b'new data');self.assertNotEqual(source_key('preview',path),old)
        cache.clear();self.assertEqual(cache.used,0)
    def test_preview_workers_do_not_queue_behind_export_pool(self):
        from PySide6.QtCore import QThreadPool
        self.assertIsNot(preview_pool(),QThreadPool.globalInstance());self.assertIsNot(preview_pool(True),preview_pool())
        self.assertLessEqual(preview_pool().maxThreadCount(),2);self.assertLessEqual(preview_pool(True).maxThreadCount(),2)
    def test_large_image_load_does_not_block_window_or_gui_and_can_cancel(self):
        path=self.root/'image.png';Image.new('RGB',(100,60),'red').save(path)
        entered=threading.Event();release=threading.Event();original=Image.open
        def slow(*args,**kwargs):
            entered.set();release.wait(4);return original(*args,**kwargs)
        with patch('image_editor.Image.open',side_effect=slow):
            editor=ImageEditor(path,lambda *args:None);editor.show()
            try:
                self.wait(entered.is_set);self.assertTrue(editor.isVisible());self.assertIsNone(editor.canvas.pixmap)
                self.assertEqual(editor.loading.bar.maximum(),0);self.assertFalse(editor.save_button.isEnabled())
                tick=[];QTimer.singleShot(0,lambda:tick.append(True));self.wait(lambda:bool(tick))
                editor.reject();self.assertTrue(editor.closed);self.assertTrue(editor.stopped.is_set());self.assertFalse(editor.isVisible())
            finally:
                release.set();preview_pool().waitForDone(5000);self.app.processEvents();editor.close()
        self.assertIsNone(editor.canvas.pixmap)
    def test_image_load_failure_is_readable_and_does_not_enable_export(self):
        editor=ImageEditor(self.root/'missing.png',lambda *args:None);self.addCleanup(editor.close);editor.show()
        self.wait(lambda:editor.load_job is None and 'nicht geöffnet' in editor.status.text())
        self.assertTrue(editor.isVisible());self.assertFalse(editor.save_button.isEnabled());self.assertFalse(editor.loading.isVisible())
    def test_reader_reuses_container_and_matches_standalone_timestamp_requests(self):
        import av
        path=self.video();expected=[read_frame(path,t,s)[1] for t,s in ((0,0),(0,1),(.1,1),(.2,-1),(1.17,0),(2.9,1))]
        original=av.open
        with patch('av.open',wraps=original) as opened:
            with FrameReader(path) as reader:
                actual=[reader.read(t,s)[1] for t,s in ((0,0),(0,1),(.1,1),(.2,-1),(1.17,0),(2.9,1))]
            self.assertEqual(actual,expected);self.assertEqual(opened.call_count,1)
    def test_sequential_thumbnails_match_covering_frames_and_bound_decode_distance(self):
        path=self.video();positions=[.15,.45,.75,1.05,1.35,2.8]
        expected=[read_frame(path,t)[1] for t in positions]
        with FrameReader(path) as reader:
            actual=[reader.read(t,max_size=(180,100),sequential=True)[1] for t in positions]
        self.assertEqual(actual,expected)
    def test_decoder_rejects_changed_source_during_session(self):
        path=self.video()
        with FrameReader(path) as reader:
            reader.read(0);s=path.stat();os.utime(path,ns=(s.st_atime_ns,s.st_mtime_ns+1000000000))
            with self.assertRaisesRegex(ValueError,'geändert'):reader.read(.1,1)
    def test_forward_frame_steps_do_not_seek_again_and_obey_cancel(self):
        path=self.video();stop=threading.Event()
        with FrameReader(path) as reader:
            reader.read(0,stopped=stop)
            seeks=[];original=reader.container
            class TrackedContainer:
                def __getattr__(self,name):return getattr(original,name)
                def seek(self,*args,**kwargs):seeks.append(args);return original.seek(*args,**kwargs)
            reader.container=TrackedContainer()
            for i in range(1,8):self.assertAlmostEqual(reader.read((i-1)/10,1,stop)[1],i/10,places=5)
            self.assertEqual(seeks,[])
            stop.set()
            with self.assertRaisesRegex(RuntimeError,'geschlossen'):reader.read(.7,1,stop)
    def test_filmstrip_reopen_uses_cache_and_reports_each_finished_thumbnail(self):
        path=self.video();stop=threading.Event();images=[];errors=[]
        first=ThumbnailJob(path,3,stop,count=4);first.signals.ready.connect(lambda i,image:images.append(i));first.signals.done.connect(errors.append);first.run()
        self.assertEqual(images,[0,1,2,3]);self.assertEqual(errors,[''])
        second=ThumbnailJob(path,3,stop,count=4);cached=[];second.signals.ready.connect(lambda i,image:cached.append(i))
        with patch('filmstrip.FrameReader',side_effect=AssertionError('Cache must avoid decoding')):second.run()
        self.assertEqual(cached,[0,1,2,3])
        stopped=threading.Event();stopped.set();third=ThumbnailJob(path,3,stopped,count=4);third.signals.ready.connect(lambda *args:self.fail('Closed preview updated'));third.run()
    def test_audio_cache_reuses_peaks_and_modified_source_invalidates(self):
        path=self.root/'audio.wav'
        with wave.open(str(path),'wb') as output:output.setnchannels(1);output.setsampwidth(2);output.setframerate(8000);output.writeframes(b'\0\0'*8000)
        job=WaveJob(path,None,threading.Event());result=[];job.signals.done.connect(lambda value,error:result.append((value,error)));job.run();self.assertEqual(result[0][1],'')
        again=WaveJob(path,None,threading.Event());hit=[];again.signals.progress.connect(hit.append)
        with patch('waveform.extract_waveform',side_effect=AssertionError('Cache must avoid decoding')):again.run()
        self.assertEqual(hit,[100]);s=path.stat();os.utime(path,ns=(s.st_atime_ns,s.st_mtime_ns+1000000000))
        third=WaveJob(path,None,threading.Event())
        with patch('waveform.extract_waveform',return_value=result[0][0]) as extract:third.run();extract.assert_called_once()

if __name__=='__main__':unittest.main()
