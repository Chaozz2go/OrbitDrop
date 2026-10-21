import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import hashlib,json,shutil,subprocess,tempfile,unittest,wave
from pathlib import Path
from unittest.mock import patch
from updater import release_info,checksum_for,download_release,verify_installer,REPOSITORY
from audio_tools import improve_audio,edge_silence,audio_settings
from local_ocr import recognize_text,ocr_pdf
from ocr_data import find_tessdata,install_languages

class DesktopReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def release(self):
        version='9.2.1';names=[f'OrbitDrop-{version}-Windows-x64-Setup.exe','SHA256SUMS.txt']
        return {'tag_name':'v'+version,'assets':[{'name':name,'browser_download_url':f'https://github.com/{REPOSITORY}/releases/download/v{version}/{name}'} for name in names],'body':'Release notes'}
    def test_update_source_validation_and_versions(self):
        data=self.release();info=release_info(data,'0.17.0');self.assertTrue(info['newer']);self.assertFalse(release_info(data,'10.0.0')['newer'])
        for change in ({'draft':True},{'prerelease':True},{'tag_name':'../9.2.1'}):
            with self.subTest(change=change),self.assertRaises(ValueError):release_info({**data,**change})
        data['assets'][0]['browser_download_url']='https://evil.invalid/Setup.exe'
        with self.assertRaises(ValueError):release_info(data)
    def test_verified_download_and_tamper_rejection(self):
        info=release_info(self.release());binary=b'MZ'+b'test installer'*200;digest=hashlib.sha256(binary).hexdigest()
        class Response:
            def __init__(self,data):self.data=data;self.headers={'Content-Length':str(len(data))}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def raise_for_status(self):pass
            def iter_content(self,size):yield self.data
        def request(url,**kwargs):return Response((digest+'  '+info['filename']+'\n').encode() if url==info['checksum_url'] else binary)
        with patch('requests.get',side_effect=request):installer=download_release(info,self.root)
        path=verify_installer(installer,self.root);self.assertEqual(path.read_bytes(),binary);path.write_bytes(b'MZchanged')
        with self.assertRaises(ValueError):verify_installer(installer,self.root)
        with patch('requests.get',side_effect=lambda url,**kw:Response(('0'*64+'  '+info['filename']).encode() if url==info['checksum_url'] else binary)),self.assertRaises(ValueError):download_release(info,self.root)
        self.assertFalse(list(self.root.rglob('*.part')))
    def test_checksum_requires_exact_filename(self):
        with self.assertRaises(ValueError):checksum_for('a'*64+'  other.exe','Setup.exe')
        with self.assertRaises(ValueError):checksum_for(('a'*64+'  Setup.exe\n')*2,'Setup.exe')
    def test_ocr_real_image_and_searchable_scan_pdf(self):
        folder=find_tessdata('eng')
        if not folder:self.skipTest('English tessdata not installed')
        import pymupdf
        image=self.root/'scan.png'
        with pymupdf.open() as doc:
            page=doc.new_page(width=400,height=180);page.insert_text((20,85),'ORBITDROP 12345',fontsize=28);page.get_pixmap(matrix=pymupdf.Matrix(2,2)).save(image)
        before=image.read_bytes();text=recognize_text(image,'eng',200,folder);self.assertIn('12345',text)
        output=ocr_pdf([image],{'language':'eng','tessdata':str(folder)},{})[0]
        with pymupdf.open(output) as pdf:self.assertIn('12345',pdf[0].get_text());self.assertEqual(len(pdf),1)
        text=recognize_text(output,'eng',200,folder);self.assertIn('12345',text);self.assertEqual(image.read_bytes(),before)
    def test_bad_ocr_download_does_not_replace_existing_models(self):
        folder=self.root/'tessdata';folder.mkdir();existing=folder/'eng.traineddata';existing.write_bytes(b'Old model')
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def raise_for_status(self):pass
            def iter_content(self,size):yield b'bad'
        with patch('requests.get',return_value=Response()),self.assertRaises(ValueError):install_languages(folder)
        self.assertEqual(existing.read_bytes(),b'Old model')
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_audio_trim_fades_and_normalization_preserve_source(self):
        from array import array
        import math
        source=self.root/'source.wav';rate=16000;samples=array('h')
        # Edge silence and an internal pause. Only the two edges may be trimmed.
        for i in range(rate*4):
            active=rate<=i<rate*2 or int(rate*2.5)<=i<rate*3.5;samples.append(int(3500*math.sin(2*math.pi*440*i/rate)) if active else 0)
        with wave.open(str(source),'wb') as wav:wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes(samples.tobytes())
        before=source.read_bytes();output=improve_audio([source],{'trim':True,'padding':.1,'fade_in':.1,'fade_out':.1,'normalize':True,'format':'WAV'},{})[0]
        import av
        with av.open(output) as audio:duration=float(audio.duration/av.time_base)
        self.assertAlmostEqual(duration,2.7,delta=.08);self.assertEqual(source.read_bytes(),before)
        before_files=set(self.root.iterdir())
        with self.assertRaises(ValueError):improve_audio([source],{'fade_in':20,'normalize':False},{})
        self.assertEqual(set(self.root.iterdir()),before_files)
    def test_edge_silence_keeps_internal_pauses_and_rejects_empty(self):
        log='silence_start: 0\nsilence_end: 1\nsilence_start: 2\nsilence_end: 3\nsilence_start: 8\nsilence_end: 10\n'
        self.assertEqual(edge_silence(log,10,.1),(.9,8.1))
        with self.assertRaises(ValueError):edge_silence('silence_start: 0\nsilence_end: 10',10,.1)
        with self.assertRaises(ValueError):audio_settings({'normalize':False})

if __name__=='__main__':unittest.main()
