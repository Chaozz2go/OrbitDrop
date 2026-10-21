import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from downloader import ProgressReporter,worker_main

class DownloadProgressTests(unittest.TestCase):
    def test_locked_snapshot_preserved_and_later_update_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'progress.json';path.write_text('{"percent": 1}')
            reporter=ProgressReporter(path)
            with patch('downloader.os.replace',side_effect=PermissionError(5,'Zugriff verweigert')),patch('downloader.time.monotonic',return_value=1):
                self.assertFalse(reporter(20,'Download'));self.assertEqual(json.loads(path.read_text())['percent'],1)
            with patch('downloader.time.monotonic',return_value=1.3):self.assertTrue(reporter(30,'Download'))
            self.assertEqual(json.loads(path.read_text())['percent'],30)
            with patch('downloader.time.monotonic',return_value=1.35):self.assertFalse(reporter(31,'Download'))
            self.assertEqual(json.loads(path.read_text())['percent'],30)
    def test_worker_finishes_even_when_progress_replace_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);staging=root/'media';staging.mkdir();config=root/'config.json';result=root/'result.json'
            config.write_text(json.dumps({'operation':'download','url':'https://example.org/video','mode':'video','staging':str(staging),'result':str(result),'progress':str(root/'progress.json')}))
            class FakeYoutubeDL:
                def __init__(self,options):self.options=options
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def extract_info(self,*args,**kwargs):
                    self.options['logger'].warning('A warning')
                    for hook in self.options['progress_hooks']:hook({'downloaded_bytes':50,'total_bytes':100})
                    (staging/'media.mp4').write_bytes(b'video-data')
                    return {'title':'Download'}
            with patch('yt_dlp.YoutubeDL',FakeYoutubeDL),patch('downloader.backend',return_value=None),patch('downloader.os.replace',side_effect=PermissionError(5,'Zugriff verweigert')):
                self.assertEqual(worker_main(config),0)
            data=json.loads(result.read_text());self.assertNotIn('error',data);self.assertEqual(Path(data['output']).read_bytes(),b'video-data')
    def test_progress_write_failure_is_nonfatal(self):
        with tempfile.TemporaryDirectory() as directory:
            reporter=ProgressReporter(Path(directory)/'progress.json')
            with patch('pathlib.Path.write_text',side_effect=PermissionError(5,'Zugriff verweigert')):self.assertFalse(reporter(50,'Download'))

if __name__=='__main__':unittest.main()
