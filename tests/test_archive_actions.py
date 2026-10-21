import io
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from archives import create_zip,extract_archive,archive_kind
from file_actions import available_file_actions
from orbitdrop import ArchiveJob

class ArchiveActionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.file=self.root/'note.txt';self.file.write_text('Hello')
        self.folder=self.root/'folder';self.folder.mkdir();(self.folder/'empty').mkdir();(self.folder/'child.txt').write_text('Child')
    def test_zip_files_folders_and_unpack(self):
        output=self.root/'selection.zip';create_zip([self.file,self.folder],output)
        self.assertEqual(archive_kind(output),'ZIP')
        with zipfile.ZipFile(output) as z:
            self.assertEqual(z.read('note.txt'),b'Hello');self.assertIn('folder/empty/',z.namelist())
        dest=self.root/'out';extract_archive(output,dest)
        self.assertEqual((dest/'note.txt').read_text(),'Hello')
        self.assertTrue((dest/'folder/empty').is_dir())
        self.assertEqual((dest/'folder/child.txt').read_text(),'Child')
        self.assertTrue(self.file.exists());self.assertTrue(self.folder.exists());self.assertTrue(output.exists())
        self.assertIn('ENTPACKEN',available_file_actions([output]))
        self.assertNotIn('ENTPACKEN',available_file_actions([output,self.file]))
        self.assertNotIn('ENTPACKEN',available_file_actions([self.folder]))
    def test_collision_and_self_inclusion(self):
        output=self.root/'selection.zip';create_zip([self.file],output);before=output.read_bytes()
        with self.assertRaises(FileExistsError):create_zip([self.file],output)
        self.assertEqual(output.read_bytes(),before)
        with self.assertRaises(ValueError):create_zip([self.folder],self.folder/'inside.zip')
        self.assertFalse((self.folder/'inside.zip').exists())
        dest=self.root/'existing';dest.mkdir();(dest/'keep').write_text('Keep')
        with self.assertRaises(FileExistsError):extract_archive(output,dest)
        self.assertEqual((dest/'keep').read_text(),'Keep')
    def test_traversal_and_symlink_and_limits(self):
        for name,link in [('../escape',False),('C:/escape',False),('..\\escape',False),('CON.txt',False),('file:stream',False),('link',True)]:
            archive=self.root/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:
                if link:
                    info=zipfile.ZipInfo(name);info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'target')
                else:z.writestr(name,'bad')
            with self.assertRaises(ValueError):extract_archive(archive,self.root/'out')
            self.assertFalse((self.root/'out').exists())
        good=self.root/'good.zip';create_zip([self.file],good)
        with patch('archives.MAX_BYTES',1):
            with self.assertRaises(ValueError):extract_archive(good,self.root/'out')
        self.assertFalse((self.root/'out').exists())
    def test_tar_gzip_and_directory_empty(self):
        for suffix,mode in [('.tar','w'),('.tar.gz','w:gz')]:
            archive=self.root/('test'+suffix)
            with tarfile.open(archive,mode) as t:t.add(self.folder,arcname='folder')
            dest=self.root/('out'+suffix)
            extract_archive(archive,dest);self.assertTrue((dest/'folder/empty').is_dir())
            self.assertEqual((dest/'folder/child.txt').read_text(),'Child')
    def test_multiple_extracts_preserve_previous_output(self):
        archive=self.root/'note.zip';create_zip([self.file],archive)
        target=self.root/'outputs';target.mkdir();existing=target/'note_entpackt';existing.mkdir();(existing/'keep').write_text('Keep')
        # Run the same job twice. Each result gets a fresh suffix, no overwrites.
        job=ArchiveJob([str(archive)],'ENTPACKEN',target);job.run()
        job=ArchiveJob([str(archive)],'ENTPACKEN',target);job.run()
        self.assertEqual((existing/'keep').read_text(),'Keep')
        self.assertEqual((target/'note_entpackt_1/note.txt').read_text(),'Hello')
        self.assertEqual((target/'note_entpackt_2/note.txt').read_text(),'Hello')

if __name__=='__main__':unittest.main()
