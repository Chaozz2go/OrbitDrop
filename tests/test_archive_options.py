import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import io,tempfile,unittest,zipfile,stat,time
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from archive_options import create_archive,list_archive,extract_options,test_archive,sevenzip
from archive_ui import ArchiveCreateDialog,ArchiveExtractDialog
from task_runtime import TaskControl,Cancelled

class ArchiveOptionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.source=self.root/'source';self.source.mkdir();(self.source/'one.txt').write_text('First '*1000);(self.source/'two.txt').write_text('Second '*1000);(self.source/'empty').mkdir();self.dest=self.root/'dest';self.dest.mkdir()
    def wait(self,condition):
        end=time.monotonic()+10
        while not condition() and time.monotonic()<end:self.app.processEvents();time.sleep(.01)
        self.assertTrue(condition())
    def test_zip_aes_password_test_and_no_password_leak(self):
        path=self.root/'secret.zip';create_archive([self.source],path,password='Secret123')
        self.assertTrue(list_archive(path));self.assertGreater(test_archive(path,'Secret123'),0)
        with self.assertRaises(Exception):extract_options(path,self.dest,password='Wrong')
        self.assertEqual(list(self.dest.iterdir()),[])
        [folder]=extract_options(path,self.dest,password='Secret123');self.assertEqual((Path(folder)/'source/one.txt').read_text(),'First '*1000)
    def test_levels_and_tar_gz_and_exclusive_outputs(self):
        uncompressed=self.root/'stored.zip';packed=self.root/'packed.zip';create_archive([self.source],uncompressed,level=0);create_archive([self.source],packed,level=9)
        self.assertGreater(uncompressed.stat().st_size,packed.stat().st_size);before=packed.read_bytes()
        with self.assertRaises(FileExistsError):create_archive([self.source],packed)
        self.assertEqual(packed.read_bytes(),before)
        path=self.root/'test.tar.gz';create_archive([self.source],path,format='TAR.GZ');self.assertGreater(test_archive(path),0);[folder]=extract_options(path,self.dest);self.assertTrue((Path(folder)/'source/empty').is_dir())
    def test_selected_entries_and_all_conflict_policies(self):
        path=self.root/'test.zip';create_archive([self.source],path)
        (self.dest/'source').mkdir();old=self.dest/'source/one.txt';old.write_text('Existing')
        for policy in ('error','skip','rename','overwrite'):
            if policy=='error':
                with self.assertRaises(FileExistsError):extract_options(path,self.dest,selected=['source/one.txt'],subfolder=False,conflict=policy)
            else:extract_options(path,self.dest,selected=['source/one.txt'],subfolder=False,conflict=policy)
            self.assertFalse((self.dest/'source/two.txt').exists())
            if policy!='overwrite':self.assertEqual(old.read_text(),'Existing')
        self.assertEqual(old.read_text(),'First '*1000);self.assertTrue((self.dest/'source/one_2.txt').exists())
    def test_unsafe_paths_links_and_expansion_limit_are_blocked(self):
        for name in ('../escape','C:/escape','folder/../../escape','file:stream','CON.txt'):
            path=self.root/'bad.zip'
            with zipfile.ZipFile(path,'w') as z:z.writestr(name,'unsafe')
            with self.assertRaises(ValueError):extract_options(path,self.dest)
            self.assertEqual(list(self.dest.iterdir()),[])
        path=self.root/'link.zip'
        with zipfile.ZipFile(path,'w') as z:
            info=zipfile.ZipInfo('link');info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'../outside')
        with self.assertRaises(ValueError):list_archive(path)
        good=self.root/'good.zip';create_archive([self.source],good)
        with patch('archive_options.MAX_BYTES',1),self.assertRaises(ValueError):extract_options(good,self.dest)
    def test_failed_overwrite_rolls_back_and_failed_recovery_keeps_backups(self):
        path=self.root/'test.zip';create_archive([self.source],path);(self.dest/'source').mkdir();a=self.dest/'source/one.txt';b=self.dest/'source/two.txt';a.write_text('OLD A');b.write_text('OLD B')
        from archive_options import move_one
        count=[0]
        def fail_once(src,dst):
            count[0]+=1
            if count[0]==4:raise OSError('Simulated failure')
            return move_one(src,dst)
        with patch('archive_options.move_one',side_effect=fail_once),self.assertRaises(OSError):extract_options(path,self.dest,subfolder=False,conflict='overwrite',selected=['source/one.txt','source/two.txt'])
        self.assertEqual(a.read_text(),'OLD A');self.assertEqual(b.read_text(),'OLD B');self.assertFalse(list(self.dest.glob('.orbit-unpack-*')))
        count[0]=0
        def fail_restore(src,dst):
            count[0]+=1
            if count[0]>=4:raise OSError('Simulated recovery failure')
            return move_one(src,dst)
        with patch('archive_options.move_one',side_effect=fail_restore),self.assertRaisesRegex(OSError,'Sicherungen bleiben'):extract_options(path,self.dest,subfolder=False,conflict='overwrite',selected=['source/one.txt','source/two.txt'])
        recovery=list(self.dest.glob('.orbit-unpack-*'));self.assertEqual(len(recovery),1);self.assertTrue((recovery[0]/'recovery.json').exists());self.assertIn(b'OLD A',[p.read_bytes() for p in (recovery[0]/'backup').iterdir()])
    def test_cancel_creation_and_extraction_leave_no_partial_results(self):
        path=self.root/'cancel.zip';control=TaskControl();control.callback=lambda percent,message:control.cancel() if message.startswith('ZIP:') else None
        with control.activate(),self.assertRaises(Cancelled):create_archive([self.source],path)
        self.assertFalse(path.exists());create_archive([self.source],path);control=TaskControl();control.callback=lambda percent,message:control.cancel() if message.startswith('Entpacken:') else None
        with control.activate(),self.assertRaises(Cancelled):extract_options(path,self.dest)
        self.assertEqual(list(self.dest.iterdir()),[])
    def test_7zip_encrypted_names_split_and_streamed_extraction(self):
        if not sevenzip():self.skipTest('7-Zip not installed')
        large=self.source/'random.bin';large.write_bytes(os.urandom(1100000));path=self.root/'native.7z';outputs=create_archive([self.source],path,format='7Z',password='Secret123',hide_names=True,split_mb=1)
        self.assertGreater(len(outputs),1);self.assertTrue(outputs[0].endswith('.001'))
        with self.assertRaises(ValueError):list_archive(outputs[0],'Wrong')
        rows=list_archive(outputs[0],'Secret123');self.assertIn('source/random.bin',[r['name'] for r in rows]);test_archive(outputs[0],'Secret123')
        [folder]=extract_options(outputs[0],self.dest,password='Secret123',selected=['source/one.txt']);self.assertEqual((Path(folder)/'source/one.txt').read_text(),'First '*1000);self.assertFalse((Path(folder)/'source/random.bin').exists())
    def test_native_windows_paths_use_stable_selection_names(self):
        archive=self.root/'fake.7z';archive.write_bytes(b'7z\xbc\xaf\x27\x1c')
        listing='Path = source\\one.txt\nSize = 12\nFolder = -\n'
        with patch('archive_options._uses_seven',return_value=True),patch('archive_options._seven',return_value=listing):
            [row]=list_archive(archive);self.assertEqual(row['name'],'source/one.txt');self.assertEqual(row['member'],'source\\one.txt')
    def test_native_dependency_is_optional_and_options_are_validated(self):
        with patch('archive_options.sevenzip',return_value=None),self.assertRaisesRegex(OSError,'7-Zip'):create_archive([self.source],self.root/'x.7z',format='7Z')
        with self.assertRaises(ValueError):create_archive([self.source],self.root/'x.tar.gz',format='TAR.GZ',password='Secret')
        with self.assertRaises(ValueError):create_archive([self.source],self.root/'x.zip',hide_names=True)
    def test_archive_dialog_options_and_selective_extract_submission(self):
        calls=[];d=ArchiveCreateDialog([self.source],lambda *args:calls.append(args));self.addCleanup(d.close);d.show();d.password.setText('Secret');d.confirm.setText('Wrong');self.assertFalse(d.start.isEnabled());d.confirm.setText('Secret');self.assertTrue(d.start.isEnabled());d.apply();self.assertEqual(calls[0][2]['password'],'Secret')
        archive=self.root/'input.zip';create_archive([self.source],archive)
        e=ArchiveExtractDialog([archive],lambda *args:calls.append(args));self.addCleanup(e.close);e.show();self.wait(lambda:e.job is None and bool(e.rows));e.select_all(False)
        for i in range(e.table.topLevelItemCount()):
            item=e.table.topLevelItem(i)
            if item.data(0,Qt.ItemDataRole.UserRole)['name']=='source/one.txt':item.setCheckState(0,Qt.CheckState.Checked)
        self.assertTrue(e.start.isEnabled());e.apply();self.assertEqual(calls[-1][2]['selected'],['source/one.txt'])

if __name__=='__main__':unittest.main()
