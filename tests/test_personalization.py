import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QEvent
from PySide6.QtTest import QTest
from PySide6.QtGui import QKeyEvent
from preferences import Preferences,DEFAULTS,pressed_mode,polling_keys,KEY_CODES
from shortcuts import normalize_shortcut
from shortcut_ui import ShortcutChoice,ShortcutCapture
from app_ui import SettingsDialog
from menu_visibility import action_catalog,visible_actions
from action_search import ActionSearchDialog
from orbitdrop import Wheel,Controller
from help_ui import HelpDialog

class PersonalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.prefs=Preferences(self.root/'prefs')
    def test_custom_keys_roundtrip_and_chord_edges(self):
        self.prefs.update(dict(self.prefs.values,convert_key='f8',edit_key=' ctrl + e ',files_key='Shift+F9'))
        values=Preferences(self.prefs.root).values;self.assertEqual([values[k] for k in ('convert_key','edit_key','files_key')],['F8','Strg+E','Shift+F9'])
        self.assertEqual(pressed_mode(values,{'Strg':True,'E':True},{'Strg':True}),'edit')
        self.assertIsNone(pressed_mode(values,{'Strg':True,'E':True},{'E':True}))
        self.assertIsNone(pressed_mode(values,{'Shift':True,'F8':True},{}))
        self.assertEqual(pressed_mode(values,{'Shift':True,'F9':True},{'Shift':True}),'files')
        self.assertEqual(set(polling_keys(values)),{'Strg','Shift','Alt','F8','E','F9'})
    def test_reject_ambiguous_system_and_altgr_chords(self):
        for key in ('Shift+F8','Shift','Alt+F4','Strg+Alt+E','Win+E','Escape','A+B'):
            with self.subTest(key=key),self.assertRaises(ValueError):self.prefs.validate(dict(self.prefs.values,edit_key=key))
        self.assertIsNone(pressed_mode(DEFAULTS,{'Strg':True,'Alt':True},{}))
    def test_capture_supports_f_key_chord_and_lone_modifier(self):
        choice=ShortcutChoice('Shift');capture=ShortcutCapture(choice);self.addCleanup(choice.close);self.addCleanup(capture.close);capture.show();capture.setFocus()
        QTest.keyClick(capture,Qt.Key.Key_F8,Qt.KeyboardModifier.ControlModifier);self.assertEqual(choice.currentText(),'Strg+F8')
        QTest.keyClick(capture,Qt.Key.Key_Shift);self.assertEqual(choice.currentText(),'Shift')
        with patch('shortcut_ui.sys.platform','win32'):
            event=QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Exclam,Qt.KeyboardModifier.ShiftModifier,0,0x31,0,'!');capture.keyPressEvent(event);capture.keyReleaseEvent(event);self.assertEqual(choice.currentText(),'Shift+1')
            event=QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_1,Qt.KeyboardModifier.KeypadModifier,0,0x61,0,'1');capture.keyPressEvent(event);capture.keyReleaseEvent(event);self.assertEqual(choice.currentText(),'Num1')

    def test_poll_custom_shortcut_and_modal_suppression(self):
        values=dict(DEFAULTS,convert_key='F8',edit_key='Strg+E',files_key='F9');controller=Controller.__new__(Controller);controller.prefs=SimpleNamespace(values=values);controller.wheel=Mock();controller.wheel.isVisible.return_value=False;controller.was_keys={};controller.selection_pending=False;controller.selection_revision=0;controller.selection_job=None;controller.released=0;controller.request_selection=Mock();controller.shortcuts_paused=False;controller.activation_guard=Mock();controller.activation_guard.context.return_value=SimpleNamespace(drag=True,selection=True,token=(1,2))
        codes={KEY_CODES['Strg'],KEY_CODES['E'],1}
        with patch('orbitdrop.sys.platform','win32'),patch('orbitdrop.ctypes.windll',SimpleNamespace(user32=SimpleNamespace(GetAsyncKeyState=lambda code:0x8000 if code in codes else 0)),create=True):controller.poll()
        controller.wheel.open.assert_called_once_with(automatic=True,mode='edit');controller.wheel.open.reset_mock();controller.was_keys={}
        with patch('orbitdrop.sys.platform','win32'),patch('orbitdrop.ctypes.windll',SimpleNamespace(user32=SimpleNamespace(GetAsyncKeyState=lambda code:0x8000)),create=True),patch('orbitdrop.QApplication.activeModalWidget',return_value=object()):controller.poll()
        controller.wheel.open.assert_not_called()
    def test_menu_settings_migrate_formats_and_save_individual_svg(self):
        self.prefs.update(dict(self.prefs.values,hidden_formats=['JPG','SVG']))
        dialog=SettingsDialog(self.prefs);self.addCleanup(dialog.close);self.assertEqual(dialog.menu_items['format:JPG'].checkState(0),Qt.CheckState.Unchecked)
        self.assertEqual(dialog.menu_items['format:SVG SCHNELL'].checkState(0),Qt.CheckState.Unchecked)
        dialog.menu_items['format:SVG SCHNELL'].setCheckState(0,Qt.CheckState.Checked)
        for key in ('edit:SCHNEIDEN','tool:TERMINAL','app:HILFE','download:VIDEO LADEN','nav:ZURÜCK','home:TOOLS'):dialog.menu_items[key].setCheckState(0,Qt.CheckState.Unchecked)
        dialog.save();values=Preferences(self.prefs.root).values;self.assertNotIn('SVG',values['hidden_formats']);self.assertIn('format:SVG ERWEITERT',values['hidden_actions']);self.assertIn('tool:TERMINAL',values['hidden_actions'])
        actions=['format:SVG SCHNELL','format:SVG ERWEITERT','edit:SCHNEIDEN','tool:TERMINAL','app:HILFE','download:VIDEO LADEN','app:ZURÜCK','TOOLS']
        self.assertEqual(visible_actions(actions,values),['format:SVG SCHNELL'])
    def test_hidden_favorites_do_not_reappear_in_wheel_or_search(self):
        self.prefs.update(dict(self.prefs.values,hidden_actions=['edit:BITMAP','tool:TERMINAL','app:HILFE','download:VIDEO LADEN'],favorite_actions=['edit:BITMAP']))
        wheel=Wheel(SimpleNamespace(prefs=self.prefs));self.addCleanup(wheel.close);wheel.files=['image.png'];wheel.kind='Bild';wheel.formats=['PNG'];wheel.mode='edit';wheel.display_mode();self.assertNotIn('edit:BITMAP',wheel.labels)
        wheel.open_link('https://example.org/movie');self.assertNotIn('download:VIDEO LADEN',wheel.labels);self.assertIn('download:AUDIO LADEN',wheel.labels)
        search=ActionSearchDialog(['edit:BITMAP','app:HILFE','app:UPDATES'],self.prefs);self.addCleanup(search.close);self.assertEqual(search.list.count(),1);self.assertEqual(search.selected(),'app:UPDATES')
    def test_all_hidden_home_renders_and_settings_still_restore(self):
        keys=[key for _,items in action_catalog(self.prefs.values) for key,_ in items];self.prefs.update(dict(self.prefs.values,hidden_actions=keys))
        wheel=Wheel(SimpleNamespace(prefs=self.prefs));self.addCleanup(wheel.close);wheel.open();self.app.processEvents();wheel.grab();self.assertEqual(wheel.labels,[]);self.assertEqual(wheel.paths,[])
        settings=SettingsDialog(self.prefs);self.addCleanup(settings.close)
        for item in settings.menu_items.values():item.setCheckState(0,Qt.CheckState.Checked)
        settings.save();self.assertEqual(self.prefs.values['hidden_actions'],[]);wheel.open();self.assertEqual(wheel.labels,['KONVERTIEREN','BEARBEITEN','TOOLS'])
    def test_help_search_and_current_bindings(self):
        self.prefs.update(dict(self.prefs.values,convert_key='F8',edit_key='Strg+E',files_key='F9'));dialog=HelpDialog(self.prefs);self.addCleanup(dialog.close)
        self.assertIn('F8',dialog.browser.toPlainText());self.assertIn('Strg+E',dialog.browser.toPlainText());dialog.query.setText('Lautheitsnormalisierung');self.assertIn('Lautheitsnormalisierung',dialog.browser.toPlainText())
        dialog.query.setText('xyz_nichtvorhanden');self.assertIn('Keine passenden Themen',dialog.browser.toPlainText());dialog.query.clear();self.assertGreaterEqual(dialog.topics.currentRow(),0)

if __name__=='__main__':unittest.main()
