import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from preferences import Preferences,DEFAULTS,KEY_CODES,pressed_mode
from orbitdrop import Wheel,Controller
from app_ui import SettingsDialog

class ShortcutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def test_default_mapping_and_migration_preserve_other_preferences(self):
        root=self.root/'old';root.mkdir();(root/'settings.json').write_text(json.dumps({'convert_key':'Shift','files_key':'Strg','image_quality':57,'download_dir':'D:/Downloads','hidden_formats':['JPG']}))
        prefs=Preferences(root);self.assertEqual([prefs.values[k] for k in ('convert_key','edit_key','files_key')],['Shift','Strg','Alt']);self.assertEqual(prefs.values['image_quality'],57);self.assertEqual(prefs.values['hidden_formats'],['JPG'])
        prefs.update(dict(prefs.values,convert_key='Alt',edit_key='Shift',files_key='Strg'));self.assertEqual(Preferences(root).values,prefs.values)
        with self.assertRaises(ValueError):prefs.update(dict(prefs.values,edit_key='Strg'))
        dialog=SettingsDialog(prefs);self.addCleanup(dialog.close);self.assertEqual(dialog.edit.currentText(),'Shift')
    def test_edges_and_altgr(self):
        for key,mode in [('Shift','convert'),('Strg','edit'),('Alt','files')]:
            self.assertEqual(pressed_mode(DEFAULTS,{key:True},{}),mode);self.assertIsNone(pressed_mode(DEFAULTS,{key:True},{key:True}))
        self.assertIsNone(pressed_mode(DEFAULTS,{'Alt':True,'Strg':True},{}))
    def test_poll_opens_direct_modes_only_during_drag(self):
        controller=Controller.__new__(Controller);controller.prefs=SimpleNamespace(values=DEFAULTS);controller.wheel=Mock();controller.wheel.isVisible.return_value=False;controller.selection_pending=False;controller.selection_revision=0;controller.selection_job=None;controller.released=0;controller.request_selection=Mock();controller.shortcuts_paused=False;controller.activation_guard=Mock();controller.activation_guard.context.return_value=SimpleNamespace(drag=True,selection=True,token=(1,2))
        for name,mode in [('Shift','convert'),('Strg','edit'),('Alt','files')]:
            controller.was_keys={key:False for key in KEY_CODES}
            def state(code):return 0x8000 if code in (KEY_CODES[name],1) else 0
            with patch('orbitdrop.sys.platform','win32'),patch('orbitdrop.ctypes.windll',SimpleNamespace(user32=SimpleNamespace(GetAsyncKeyState=state)),create=True):controller.poll()
            controller.wheel.open.assert_called_with(automatic=mode!='files',mode=mode)
        controller.wheel.open.reset_mock();controller.was_keys={key:False for key in KEY_CODES}
        with patch('orbitdrop.sys.platform','win32'),patch('orbitdrop.ctypes.windll',SimpleNamespace(user32=SimpleNamespace(GetAsyncKeyState=lambda code:0x8000 if code==KEY_CODES['Alt'] else 0)),create=True):controller.poll()
        controller.wheel.open.assert_not_called()
    def test_direct_context_and_switch_reject_stale_probe(self):
        source=self.root/'image.png';Image.new('RGB',(80,40),'red').save(source)
        wheel=Wheel(object());self.addCleanup(wheel.close);wheel.open(automatic=True,mode='convert');wheel.inspect([str(source)])
        wheel.switch_mode('files');self.assertIn('tool:TERMINAL',wheel.labels);self.assertNotIn('edit:ZUSCHNEIDEN',wheel.labels);self.assertTrue(wheel.automatic)
        wheel.select_action('app:ZURÜCK');wheel.select_action('BEARBEITEN');deadline=time.monotonic()+5
        while wheel.checking and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        self.assertFalse(wheel.checking);self.assertIn('edit:ZUSCHNEIDEN',wheel.labels);self.assertNotIn('format:PNG',wheel.labels);self.assertNotIn('tool:TERMINAL',wheel.labels)
        wheel.switch_mode('convert')
        while wheel.checking and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        self.assertIn('format:PNG',wheel.labels);self.assertEqual(wheel.files,[str(source)])
        wheel.select_action('format:ZURÜCK');wheel.switch_mode('convert');self.assertEqual(wheel.node,'direct');self.assertIn('format:PNG',wheel.labels)
        for kind in ('Video','Audio'):
            wheel.mode='edit';wheel.inspected(object(),wheel.revision,['MP3'],(kind,''));self.assertIn('edit:SCHNEIDEN',wheel.labels);self.assertNotIn('edit:ZUSCHNEIDEN',wheel.labels)

if __name__=='__main__':unittest.main()
