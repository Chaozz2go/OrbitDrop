import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QUrl,QPointF,QMimeData
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from PySide6.QtWidgets import QApplication
from file_actions import (FILE_ACTIONS,available_file_actions,file_mime,copy_paths_text,containing_folders,
                         plan_moves,execute_moves,terminal_commands,explorer_commands)
from shelf import Shelf
from orbitdrop import Wheel

class FileActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=self.root/'source';self.source.mkdir()
        self.file=self.source/'test & $file.txt';self.file.write_text('Original')
        self.folder=self.source/'Folder';self.folder.mkdir();(self.folder/'child.txt').write_text('Child')
        self.dest=self.root/'target';self.dest.mkdir()

    def test_file_clipboard_and_path_text(self):
        mime=file_mime([self.file,self.folder])
        self.assertEqual([Path(url.toLocalFile()) for url in mime.urls()],[self.file,self.folder])
        self.assertEqual(bytes(mime.data('application/x-qt-windows-mime;value="Preferred DropEffect"')),struct.pack('<I',1))
        self.assertEqual(copy_paths_text([self.file,self.folder]),str(self.file)+'\n'+str(self.folder))
        self.assertEqual(containing_folders([self.file,self.file,self.folder]),[self.source,self.folder])
        self.assertEqual(self.file.read_text(),'Original')

    def test_move_files_and_folders(self):
        plans=plan_moves([self.file,self.folder],self.dest)
        outputs,errors=execute_moves(plans)
        self.assertEqual(errors,[]);self.assertEqual(len(outputs),2)
        self.assertFalse(self.file.exists());self.assertFalse(self.folder.exists())
        self.assertEqual((self.dest/self.file.name).read_text(),'Original')
        self.assertEqual((self.dest/'Folder/child.txt').read_text(),'Child')

    def test_conflict_preflight_and_no_overwrite(self):
        target=self.dest/self.file.name;target.write_text('Existing')
        with self.assertRaises(FileExistsError):plan_moves([self.file,self.folder],self.dest)
        self.assertTrue(self.folder.exists());self.assertEqual(self.file.read_text(),'Original')
        self.assertEqual(target.read_text(),'Existing')
        target.unlink();plans=plan_moves([self.file,self.folder],self.dest)
        target.write_text('Race conflict')
        outputs,errors=execute_moves(plans)
        self.assertEqual(outputs,[]);self.assertTrue(errors)
        self.assertEqual(target.read_text(),'Race conflict');self.assertTrue(self.file.exists());self.assertTrue(self.folder.exists())
        with self.assertRaises(ValueError):plan_moves([self.folder],self.folder)
        with self.assertRaises(ValueError):plan_moves([self.folder,self.folder/'child.txt'],self.dest)

    def test_failure_preserves_original(self):
        plans=plan_moves([self.file],self.dest)
        with patch('file_actions.copy_stream',side_effect=OSError('Disk full')):
            # Exercise the cross-volume fallback directly on all test platforms.
            from file_actions import _copy_then_remove
            with self.assertRaises(OSError):_copy_then_remove(*plans[0])
        self.assertEqual(self.file.read_text(),'Original');self.assertFalse(plans[0][1].exists())

    def test_terminal_and_explorer_paths_are_arguments(self):
        with patch('file_actions.sys.platform','win32'),patch('file_actions.shutil.which',return_value='wt.exe'):
            commands=terminal_commands([self.file,self.folder])
            self.assertEqual(commands[0],(['wt.exe','-d',str(self.source)],str(self.source)))
            self.assertEqual(commands[1][0][-1],str(self.folder))
            explorer=explorer_commands([self.file])
            self.assertEqual(explorer[0][-2:],['/select,',str(self.file)])

    def test_shelf_is_reference_only(self):
        shelf=Shelf();self.addCleanup(shelf.close)
        shelf.list.add_paths([self.file,self.folder,self.file])
        self.assertEqual(shelf.list.count(),2)
        shelf.list.item(0).setSelected(True);shelf.list.remove_selected()
        self.assertEqual(shelf.list.count(),1);self.assertTrue(self.file.exists())
        shelf.clear();self.assertEqual(shelf.list.count(),0);self.assertTrue(self.folder.exists())

    def test_file_wheel_accepts_folders_and_unknown_formats(self):
        calls=[]
        class Controller:
            def file_action(self,files,target):calls.append((files,target))
        wheel=Wheel(Controller());self.addCleanup(wheel.close)
        wheel.open(mode='files');self.app.processEvents()
        self.assertIn('app:EINSTELLUNGEN',wheel.all_actions)
        self.assertNotIn('tool:ENTPACKEN',wheel.all_actions)
        unknown=self.source/'unknown.xyz';unknown.write_text('arbitrary bytes')
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(self.folder)),QUrl.fromLocalFile(str(unknown))])
        enter=QDragEnterEvent(QPointF(190,190).toPoint(),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        wheel.dragEnterEvent(enter)
        self.assertTrue(enter.isAccepted());self.assertFalse(wheel.checking)
        # First segment: ZIP. Action is deferred until OLE returns.
        from direct_wheel import geometry
        point=next(entry[2] for entry in geometry(wheel) if entry[0]=='tool:ZIP')
        drop=QDropEvent(point,Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        wheel.dropEvent(drop);self.assertEqual(calls,[])
        self.app.processEvents()
        self.assertEqual([([Path(p) for p in paths],action) for paths,action in calls],[([self.folder,unknown],'ZIP')])

if __name__=='__main__':unittest.main()
