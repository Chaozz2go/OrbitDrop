import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from converter import convert
from filetypes import inspect_file, common_actions

class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root/'disguised.mp4'
        Image.new('RGB', (32, 32), 'red').save(self.image, format='PNG')

    def test_content_over_extension(self):
        self.assertEqual(inspect_file(self.image).kind, 'Bild')
        fake = self.root/'fake.png'
        fake.write_text('This is not an image')
        self.assertEqual(inspect_file(fake).actions, ())
        with self.assertRaises(ValueError):
            convert(fake, 'PNG')

    def test_unknown_mixed_and_missing_backend(self):
        other = self.root/'unknown.bin'
        other.write_text('hello')
        with patch('filetypes.backend', return_value=None):
            self.assertEqual(inspect_file(self.image).kind, 'Bild')
            self.assertEqual(common_actions([self.image, other])[0], ())
            self.assertEqual(common_actions([])[0], ())
            self.assertIn('ffmpeg', inspect_file(other).message)

    def test_pdf_text(self):
        from reportlab.pdfgen.canvas import Canvas
        pdf = self.root/'document.bin'
        c = Canvas(str(pdf)); c.drawString(30, 700, 'OrbitDrop test text'); c.save()
        self.assertIn('TXT', inspect_file(pdf).actions)
        self.assertIn('OrbitDrop test text', convert(pdf, 'TXT').read_text())

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg missing')
    def test_real_video_audio_and_intersection(self):
        video = self.root/'video.dat'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=red:s=32x32:r=5',
                        '-f', 'lavfi', '-i', 'sine=frequency=400', '-t', '0.5', '-c:v', 'libx264',
                        '-c:a', 'aac', '-f', 'mp4', str(video)], check=True)
        info = inspect_file(video)
        self.assertEqual(info.kind, 'Video')
        self.assertNotIn('JPG', info.actions)
        self.assertIn('STANDBILD', info.actions)
        for action in info.actions:
            output = convert(video, action)
            self.assertGreater(output.stat().st_size, 0)
            expected = 'Bild' if action == 'STANDBILD' else 'Video' if action in ('MP4', 'WEBM','MOV','MKV','AVI','WMV','GIF') else 'Audio'
            self.assertEqual(inspect_file(output).kind, expected)
        audio = convert(video, 'WAV')
        self.assertEqual(common_actions([video, audio])[0], ('MP3','M4A','WAV','FLAC','OGG','OPUS','AIFF','WMA'))
        self.assertEqual(common_actions([self.image, video])[0], ())
        silent = self.root/'silent.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video), '-an', '-c:v', 'copy', str(silent)], check=True)
        self.assertNotIn('MP3', inspect_file(silent).actions)

if __name__ == '__main__':
    unittest.main()
