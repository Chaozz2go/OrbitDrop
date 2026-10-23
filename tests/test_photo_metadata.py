import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,time,unittest
from pathlib import Path
from PIL import Image
from photo_metadata import collect_files,metadata_plan,image_metadata
from batch_rename import rename_with_journal,undo_journal,latest_journal,execute_renames
from PySide6.QtWidgets import QApplication
from rename_ui import RenameDialog

class PhotoMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def photo(self,name='photo.jpg',date='2026:10:23 18:42:05'):
        path=self.root/name;exif=Image.Exif()
        if date:exif[36867]=date
        exif[272]='Camera / Model';Image.new('RGB',(16,12),'red').save(path,exif=exif);return path
    def wait(self,condition):
        end=time.monotonic()+10
        while not condition() and time.monotonic()<end:self.app.processEvents();time.sleep(.01)
        self.assertTrue(condition())
    def test_exif_name_camera_date_and_unmodified_contents(self):
        source=self.photo();before=source.read_bytes();plans,rows=metadata_plan([source],'{date}_{time}_{camera}_{n}')
        self.assertEqual(plans[0][1].name,'2026-10-23_18-42-05_Camera _ Model_001.jpg');self.assertIn('EXIF',rows[0][2])
        outputs,journal=rename_with_journal(plans,self.root/'state');self.assertEqual(Path(outputs[0]).read_bytes(),before)
        self.assertEqual(latest_journal(self.root/'state'),journal);undo_journal(journal);self.assertEqual(source.read_bytes(),before);self.assertIsNone(latest_journal(self.root/'state'))
    def test_missing_exif_never_implicitly_uses_file_date(self):
        source=self.photo(date=None)
        for mode in ('skip','keep'):
            plans,rows=metadata_plan([source],'{date}_{n}',missing=mode);self.assertEqual(plans,[]);self.assertIn('EXIF fehlt',rows[0][2])
        plans,rows=metadata_plan([source],'{date}_{n}',missing='mtime');self.assertIn('Änderungsdatum',rows[0][2]);self.assertNotEqual(plans[0][1].name,source.name)
    def test_recursive_folder_images_only_and_parent_names_unchanged(self):
        self.photo();folder=self.root/'sub';folder.mkdir();Image.new('RGB',(8,8)).save(folder/'inside.png');(folder/'note.txt').write_text('keep')
        files,_=collect_files([self.root],images_only=True);self.assertEqual(len(files),1)
        files,ignored=collect_files([self.root,self.root/'sub'],recursive=True,images_only=True);self.assertEqual(len(files),2);self.assertEqual(ignored,2)
        plans,rows=metadata_plan(files,'Image_{n}');execute_renames(plans);self.assertTrue(folder.is_dir());self.assertTrue((folder/'note.txt').exists())
    def test_duplicate_names_are_numbered_and_existing_file_is_preserved(self):
        a=self.photo('one.jpg');b=self.photo('two.jpg');occupied=self.root/'2026-10-23.jpg';occupied.write_text('Existing')
        plans,_=metadata_plan([a,b],'{date}');self.assertEqual([p[1].name for p in plans],['2026-10-23_2.jpg','2026-10-23_3.jpg'])
        execute_renames(plans);self.assertEqual(occupied.read_text(),'Existing')
    def test_persistent_undo_rejects_modified_result(self):
        source=self.photo();plans,_=metadata_plan([source],'{date}');outputs,journal=rename_with_journal(plans,self.root/'state');target=Path(outputs[0]);target.write_bytes(b'Changed externally')
        with self.assertRaisesRegex(ValueError,'geändert'):undo_journal(journal)
        self.assertEqual(target.read_bytes(),b'Changed externally');self.assertFalse(source.exists())
    def test_reparse_or_symlink_folder_is_not_followed(self):
        real=self.root/'real';real.mkdir();Image.new('RGB',(8,8)).save(real/'x.png');link=self.root/'link'
        try:link.symlink_to(real,target_is_directory=True)
        except OSError:self.skipTest('Symlinks unavailable')
        with self.assertRaises(ValueError):collect_files([link],recursive=True)
        files,_=collect_files([self.root],recursive=True,images_only=True);self.assertEqual(len(files),1)
    def test_invalid_patterns_do_not_move_anything(self):
        source=self.photo()
        for pattern in ('../{date}','{unknown}','CON','{date:%Y}'):
            with self.subTest(pattern=pattern),self.assertRaises(ValueError):metadata_plan([source],pattern)
        self.assertTrue(source.exists())
    def test_folder_ui_preview_missing_date_and_persistent_undo(self):
        source=self.photo();state=self.root/'state';d=RenameDialog([self.root],state);self.addCleanup(d.close);d.show();d.template.setCurrentIndex(1)
        self.wait(lambda:d.start.isEnabled());self.assertEqual(d.plans[0][1].name,'2026-10-23_18-42-05.jpg');d.apply();self.wait(lambda:d.job is None)
        target=Path(d.files[0]);self.assertTrue(target.exists());d.close();again=RenameDialog([target],state);self.addCleanup(again.close)
        self.assertTrue(again.undo.isEnabled());again.restore();self.wait(lambda:again.job is None);self.assertTrue(source.exists());self.assertFalse(target.exists())

if __name__=='__main__':unittest.main()
