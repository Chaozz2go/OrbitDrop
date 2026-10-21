import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json,tempfile,unittest,shutil,subprocess
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from downloader import playlist_summary,worker_main
from download_ui import DownloadDialog
from orbitdrop import DownloadJob,Controller
from task_runtime import Cancelled

class PlaylistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def sample(self):
        return {'_type':'playlist','title':'Meine Playlist','extractor_key':'YoutubeTab','entries':[
            {'id':'abcdefghijk','title':'Erster Song','duration':65,'url':'abcdefghijk'},
            {'id':'lmnopqrstuv','title':'[Private video]','availability':'private'},
            {'id':'0123456789_','title':'Dritter Song','duration':3661,'url':'https://www.youtube.com/watch?v=0123456789_&list=PLtest'},
            None]}
    def test_playlist_order_unavailable_and_stable_single_video_links(self):
        info=playlist_summary(self.sample());self.assertTrue(info['playlist']);self.assertEqual([e['index'] for e in info['entries']],[1,2,3,4]);self.assertEqual([e['available'] for e in info['entries']],[True,False,True,False]);self.assertEqual(info['entries'][2]['url'],'https://www.youtube.com/watch?v=0123456789_')
        with self.assertRaises(ValueError):playlist_summary({'entries':[]})
        with self.assertRaises(ValueError):playlist_summary({'entries':({} for _ in range(10001))})
    def test_flat_worker_inspection_returns_entries_and_does_not_download(self):
        sample=self.sample();seen={}
        class Fake:
            def __init__(self,options):seen.update(options)
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def extract_info(self,url,download):
                if download:raise AssertionError('Inspection must never download')
                return sample
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);config=root/'request.json';result=root/'result.json';config.write_text(json.dumps({'operation':'inspect','url':'https://www.youtube.com/playlist?list=PLx','result':str(result),'progress':str(root/'progress.json')}))
            with patch('yt_dlp.YoutubeDL',Fake),patch('downloader.backend',return_value=None):self.assertEqual(worker_main(config),0)
            self.assertEqual(len(json.loads(result.read_text())['entries']),4);self.assertFalse(seen['noplaylist']);self.assertEqual(seen['extract_flat'],'in_playlist')
    def test_dialog_select_all_none_subset_and_url_invalidation(self):
        with tempfile.TemporaryDirectory() as d:
            calls=[];dialog=DownloadDialog(None,'audio',d,lambda *a:calls.append(a));self.addCleanup(dialog.close)
            url='https://www.youtube.com/playlist?list=PLx';dialog.url.setText(url);dialog.inspected(url,playlist_summary(self.sample()),'');dialog.show();self.app.processEvents()
            self.assertTrue(dialog.playlist_panel.isVisible());self.assertEqual(len(dialog.selected_entries()),2);self.assertTrue(dialog.entries.topLevelItem(1).isDisabled())
            dialog.select_entries(False);self.assertFalse(dialog.start.isEnabled());dialog.select_entries(True);self.assertEqual(len(dialog.selected_entries()),2)
            dialog.entries.topLevelItem(0).setCheckState(0,Qt.CheckState.Unchecked);dialog.search.setText('Erster');self.assertEqual(len(dialog.selected_entries()),1)
            dialog.download();self.assertEqual(len(calls),1);self.assertEqual([e['index'] for e in calls[0][4]],[3])
            other=DownloadDialog(None,'video',d,lambda *a:None);self.addCleanup(other.close);other.url.setText(url);other.inspected(url,playlist_summary(self.sample()),'');other.url.setText('https://example.org/new');self.assertFalse(other.start.isEnabled());self.assertIsNone(other.info)
    def test_sequential_job_keeps_successes_and_reports_failure(self):
        entries=playlist_summary(self.sample())['entries'];entries=[entries[0],entries[2]]
        job=DownloadJob('https://example.org/playlist','audio','.',0,entries)
        with patch('downloader.download_link',side_effect=[ValueError('Not available'),['third.mp3']]) as download:job.run()
        self.assertEqual(download.call_count,2);self.assertEqual(job.outputs,['third.mp3']);self.assertIn('Erster Song',job.errors[0]);self.assertIn('Not available',job.errors[0])
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_real_playlist_downloads_only_selected_media(self):
        import functools,http.server,threading
        from downloader import inspect_link
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);output=root/'out';output.mkdir();requests=[]
            for name,length in [('one',.5),('two',.9)]:
                subprocess.run([shutil.which('ffmpeg'),'-v','error','-f','lavfi','-i',f'color=s=96x64:r=10:d={length}','-f','lavfi','-i',f'sine=duration={length}','-c:v','libx264','-c:a','aac','-shortest',str(root/(name+'.mp4'))],check=True)
            (root/'index.html').write_text('<title>Local playlist</title><video src="one.mp4" controls></video><video src="two.mp4" controls></video>')
            class Handler(http.server.SimpleHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):requests.append(self.path);super().do_GET()
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=d));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                url=f'http://127.0.0.1:{server.server_port}/index.html';info=inspect_link(url);self.assertEqual(len(info['entries']),2);self.assertTrue(info['entries'][1]['url'].endswith('/two.mp4'));requests.clear()
                job=DownloadJob(url,'audio',str(output),0,[info['entries'][1]]);job.run();self.assertFalse(job.errors);self.assertEqual(len(job.outputs),1)
                self.assertIn('/two.mp4',requests);self.assertNotIn('/one.mp4',requests);self.assertEqual(len(list(output.iterdir())),1)
            finally:server.shutdown();server.server_close();thread.join()

    def test_cancel_preserves_completed_tracks_and_skips_remaining(self):
        entries=[{'url':'https://example.org/'+str(i),'title':str(i)} for i in range(3)];job=DownloadJob('https://example.org/playlist','audio','.',0,entries)
        def download(url,*args):
            if url.endswith('/1'):job.control.cancel();raise Cancelled()
            return [url.rsplit('/',1)[-1]+'.mp3']
        with patch('downloader.download_link',side_effect=download) as call:job.run()
        self.assertEqual(call.call_count,2);self.assertEqual(job.outputs,['0.mp3']);self.assertTrue(job.was_cancelled)

if __name__=='__main__':unittest.main()
