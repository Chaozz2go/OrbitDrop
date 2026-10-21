import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,threading,time,unittest
from pathlib import Path
from PIL import Image
from PySide6.QtWidgets import QApplication
from compression_ui import CompressionDialog
from compression_advice import inspect_compression,compression_advice
from orbit_compression import compression_settings
from preferences import Preferences

class CompressionGuidanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def test_slider_updates_real_limit_and_preserves_original(self):
        path=self.root/'noise.png';Image.effect_noise((320,200),80).convert('RGB').save(path);before=path.read_bytes()
        dialog=CompressionDialog([str(path)],'Bild',lambda *a:None,Preferences(self.root/'prefs'));self.addCleanup(dialog.close)
        self.assertIn('Aktuelle Größe',dialog.size_summary.text());dialog.target_slider.setValue(50)
        self.assertAlmostEqual(dialog.parameters()['target_mb']*1e6,len(before)*.5,delta=501)
        self.assertIn('50 %',dialog.target_description.text());dialog.show();end=time.monotonic()+10
        while (dialog.preview_image is None or dialog.job) and time.monotonic()<end:self.app.processEvents();time.sleep(.01)
        self.assertIsNotNone(dialog.preview_image);self.assertTrue(dialog.start.isEnabled());self.assertIn('kleiner',dialog.advice.text())
        dialog.target.setValue(0);self.assertEqual(dialog.parameters()['target_mb'],0);self.assertIn('Kein Größenlimit',dialog.target_description.text());self.assertEqual(path.read_bytes(),before)
    def test_media_budget_rejects_impossible_target_and_warns_low_bitrate(self):
        records=[dict(name='clip.mp4',size=10_000_000,duration=120,audio=True)]
        text,allowed=compression_advice('Video',records,compression_settings({'target_mb':.1}));self.assertFalse(allowed);self.assertIn('zu klein',text)
        text,allowed=compression_advice('Video',records,compression_settings({'target_mb':2}));self.assertTrue(allowed);self.assertIn('sichtbare Verluste',text)
        text,allowed=compression_advice('Audio',records,compression_settings({'target_mb':1}));self.assertTrue(allowed);self.assertIn('hörbar',text)
        text,allowed=compression_advice('Audio',records,compression_settings({'target_mb':.1}));self.assertFalse(allowed)
    def test_pdf_probe_writes_no_user_output_and_checks_limit(self):
        import pymupdf
        path=self.root/'source.pdf'
        with pymupdf.open() as pdf:pdf.new_page().insert_text((20,40),'OrbitDrop');pdf.save(path)
        before=path.read_bytes();records=inspect_compression([path],'PDF',threading.Event())
        self.assertGreater(records[0]['optimized'],0);self.assertEqual(path.read_bytes(),before);self.assertEqual(list(self.root.iterdir()),[path])
        text,allowed=compression_advice('PDF',records,compression_settings({'target_mb':.000001}));self.assertFalse(allowed);self.assertIn('nicht erreicht',text)
    def test_mixed_batch_checks_every_duration(self):
        records=[dict(name='short.wav',size=1_000_000,duration=5,audio=True),dict(name='long.wav',size=20_000_000,duration=600,audio=True)]
        text,allowed=compression_advice('Audio',records,compression_settings({'target_mb':1}));self.assertFalse(allowed);self.assertIn('long.wav',text)

if __name__=='__main__':unittest.main()
