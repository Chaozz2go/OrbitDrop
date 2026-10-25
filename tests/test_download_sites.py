"""Provider-independent extraction, format handling and real generic media."""
import functools
import http.server
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from downloader import inspect_link,download_link,playlist_summary,worker_main
from link_selection import media_link


class DownloadSiteTests(unittest.TestCase):
    def test_accepts_other_providers_without_domain_allowlist(self):
        for url in ('https://vimeo.com/123456789','https://soundcloud.com/artist/song',
                    'https://www.twitch.tv/videos/123456789','https://example.org/embedded-media'):
            with self.subTest(url=url),patch('downloader.invoke_worker',return_value={'title':'Media'}) as worker:
                self.assertEqual(media_link(url),url)
                self.assertEqual(inspect_link(url),{'title':'Media'})
                worker.assert_called_once_with({'operation':'inspect','url':url})

    def test_provider_playlists_keep_public_pages_and_relative_links(self):
        info=playlist_summary({'_type':'playlist','extractor_key':'SoundcloudSet',
            'webpage_url':'https://soundcloud.com/artist/sets/album','entries':[
                {'title':'Song','webpage_url':'https://soundcloud.com/artist/song',
                 'url':'https://cdn.example.org/expired.mp3?signature=old'},
                {'title':'Second','url':'../../artist/second'},
                {'title':'Direct','url':'https://cdn.example.org/direct.opus'},
                {'title':'Private','url':'https://soundcloud.com/artist/private','availability':'private'}]})
        self.assertEqual([e['url'] for e in info['entries']],[
            'https://soundcloud.com/artist/song','https://soundcloud.com/artist/second',
            'https://cdn.example.org/direct.opus','https://soundcloud.com/artist/private'])
        self.assertEqual([e['available'] for e in info['entries']],[True,True,True,False])
        embedded=playlist_summary({'_type':'playlist','entries':[
            {'title':'Second video','webpage_url':'https://example.org/collection',
             'url':'https://cdn.example.org/second.mp4'}]},'https://example.org/collection')
        self.assertEqual(embedded['entries'][0]['url'],'https://cdn.example.org/second.mp4')

    def test_worker_keeps_all_extractors_and_accepts_provider_media_formats(self):
        for extension in ('wmv','3gp','mpeg','m4a','opus','flac','ts'):
            with self.subTest(extension=extension),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);staging=root/'staging';staging.mkdir();seen={}
                config=root/'request.json';result=root/'result.json'
                url='https://example.org/provider/media'
                config.write_text(json.dumps({'operation':'download','url':url,'mode':'video',
                    'height':720,'staging':str(staging),'result':str(result),'progress':str(root/'progress.json')}),encoding='utf-8')
                class Fake:
                    def __init__(self,options):seen.update(options)
                    def __enter__(self):return self
                    def __exit__(self,*args):pass
                    def extract_info(self,target,download):
                        if target!=url or not download:raise AssertionError('URL changed')
                        (staging/('media.'+extension)).write_bytes(b'provider media')
                        return {'title':'Provider media'}
                with patch('yt_dlp.YoutubeDL',Fake),patch('downloader.backend',return_value=None):
                    self.assertEqual(worker_main(config),0)
                data=json.loads(result.read_text(encoding='utf-8'))
                self.assertEqual(Path(data['output']).suffix,'.'+extension)
                self.assertNotIn('allowed_extractors',seen)
                self.assertTrue(seen['format'].endswith('/bestvideo[height<=720]'))

    def test_video_codec_without_resolution_is_still_recognized(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config=root/'request.json';result=root/'result.json'
            config.write_text(json.dumps({'operation':'inspect','url':'https://example.org/video',
                'result':str(result),'progress':str(root/'progress.json')}),encoding='utf-8')
            class Fake:
                def __init__(self,options):pass
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def extract_info(self,*args,**kwargs):
                    return {'title':'No dimensions','formats':[{'ext':'unknown','vcodec':'h264','acodec':'none'}]}
            with patch('yt_dlp.YoutubeDL',Fake),patch('downloader.backend',return_value=None):
                self.assertEqual(worker_main(config),0)
            data=json.loads(result.read_text(encoding='utf-8'))
            self.assertTrue(data['video']);self.assertFalse(data['audio'])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_real_generic_embedded_audio_and_silent_video(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'out';output.mkdir()
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=0.4',
                '-c:a','aac',str(root/'audio.m4a')],check=True)
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=s=96x64:r=10:d=0.4',
                '-c:v','wmv2',str(root/'silent.wmv')],check=True)
            (root/'index.html').write_text('<title>Embedded audio</title><audio controls src="audio.m4a"></audio>',encoding='utf-8')
            class Handler(http.server.SimpleHTTPRequestHandler):
                def log_message(self,*args):pass
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=directory))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                base=f'http://127.0.0.1:{server.server_port}'
                info=inspect_link(base+'/index.html');self.assertTrue(info['audio']);self.assertFalse(info['video'])
                audio=download_link(base+'/index.html','audio',output)
                self.assertEqual(Path(audio[0]).suffix,'.mp3');self.assertGreater(Path(audio[0]).stat().st_size,100)
                info=inspect_link(base+'/silent.wmv');self.assertTrue(info['video'])
                video=download_link(base+'/silent.wmv','video',output)
                result=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type',
                    '-of','json',video[0]],capture_output=True,text=True,check=True)
                self.assertEqual([s['codec_type'] for s in json.loads(result.stdout)['streams']],['video'])
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
