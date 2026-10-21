import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from media_setup import verify_checksum,install_archive
from filetypes import inspect_file,backend

class MediaSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def test_checksum_and_fixed_outputs(self):
        archive=self.root/'ffmpeg.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('ffmpeg-build/bin/ffmpeg.exe',b'MZexample')
            z.writestr('ffmpeg-build/bin/ffprobe.exe',b'MZexample-probe')
            z.writestr('../../escape','Do not extract')
        checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
        verify_checksum(archive,checksum+' ffmpeg.zip')
        with self.assertRaises(ValueError):verify_checksum(archive,'0'*64)
        with self.assertRaises(ValueError):verify_checksum(archive,'invalid')
        target=self.root/'bin';install_archive(archive,target)
        self.assertEqual(sorted(p.name for p in target.iterdir()),['ffmpeg.exe','ffprobe.exe'])
        self.assertEqual((target/'ffmpeg.exe').read_bytes(),b'MZexample')
    def test_broken_package_does_not_replace_existing(self):
        target=self.root/'bin';target.mkdir();(target/'ffmpeg.exe').write_bytes(b'Old')
        archive=self.root/'bad.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('build/bin/ffmpeg.exe',b'MZincomplete')
        with self.assertRaises(ValueError):install_archive(archive,target)
        self.assertEqual((target/'ffmpeg.exe').read_bytes(),b'Old')
    def test_mp4_without_media_backend_is_identified_but_not_offered(self):
        file=self.root/'video.mp4';file.write_bytes(b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42')
        with patch('filetypes.backend',return_value=None):
            info=inspect_file(file)
        self.assertEqual(info.kind,'MP4/MOV');self.assertEqual(info.actions,())
        self.assertIn('Medienkonverter fehlt',info.message)
        self.assertIn('Medien-einrichten.cmd',info.message)
    def test_probe_failure_is_visible(self):
        file=self.root/'damaged.mp4';file.write_bytes(b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42')
        with patch('filetypes.backend',return_value='fake'),patch('filetypes.run',return_value=subprocess.CompletedProcess([],1,'','moov atom not found')):
            info=inspect_file(file)
        self.assertIn('moov atom not found',info.message)

if __name__=='__main__':unittest.main()
