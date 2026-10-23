import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication,QLabel
from PySide6.QtCore import QPoint
from preferences import Preferences,DEFAULTS
from clipboard_shortcut import ClipboardGesture,youtube_link
from activation_guard import ActivationContext
from orbitdrop import Controller
from welcome_ui import WelcomeDialog

URL='https://www.youtube.com/watch?v=abc123'

class ClipboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_only_youtube_urls_and_no_credentials_or_lookalike_hosts(self):
        for url in (URL,'https://youtu.be/abc','https://music.youtube.com/watch?v=abc','https://m.youtube.com/shorts/abc'):
            self.assertEqual(youtube_link(url),url)
        for url in ('file:///x','https://youtube.com.evil.test/v','https://notyoutube.com/v','https://u:p@youtube.com/v','hello','https://example.org/v',URL+' other text'):
            self.assertIsNone(youtube_link(url))
    def test_click_works_in_both_orders_and_clipboard_is_read_only_on_gesture(self):
        for key_first in (True,False):
            g=ClipboardGesture();read=Mock(return_value=URL)
            g.update(False,key_first,(10,10),(1,2),read,now=0);read.assert_not_called()
            if not key_first:g.update(True,False,(10,10),(1,2),read,now=.1)
            self.assertEqual(g.update(True,True,(10,10),(1,2),read,now=.2)[0],'pending')
            self.assertEqual(g.update(False,True,(11,11),(1,2),read,now=.3),('click',URL))
            self.assertEqual(g.update(False,True,(11,11),(1,2),read,now=.4),(None,None))
    def test_drag_focus_timeout_key_release_and_changed_clipboard_cancel(self):
        for left,held,point,token,now,phase in [(True,True,(40,10),(1,2),.2,'drag'),(False,True,(10,10),(9,9),.2,None),(False,True,(10,10),(1,2),2,None),(False,False,(10,10),(1,2),.2,None)]:
            g=ClipboardGesture();g.update(True,True,(10,10),(1,2),lambda:URL,now=0)
            self.assertEqual(g.update(left,held,point,token,lambda:URL,now=now)[0],phase)
        g=ClipboardGesture();g.update(True,True,(10,10),(1,2),lambda:URL,now=0)
        self.assertIsNone(g.update(False,True,(10,10),(1,2),lambda:'https://youtu.be/changed',now=.2)[0])
    def test_file_already_moved_before_modifier_never_becomes_a_clipboard_click(self):
        g=ClipboardGesture();read=Mock(return_value=URL)
        g.update(True,False,(10,10),(1,2),read,now=0)
        self.assertEqual(g.update(True,True,(70,10),(1,2),read,now=.2),(None,None))
        self.assertEqual(g.update(False,True,(70,10),(1,2),read,now=.3),(None,None))
        read.assert_not_called()
        g=ClipboardGesture();g.update(True,True,(10,10),(1,2),read,now=0)
        self.assertEqual(g.update(True,True,(10,10),(1,2),read,now=2)[0],'drag')
    def controller(self):
        c=Controller.__new__(Controller);c.prefs=SimpleNamespace(values=dict(DEFAULTS));c.clipboard_gesture=ClipboardGesture();c.selection_revision=0
        c.wheel=Mock();c.wheel.isVisible.return_value=False;c.wheel.files=[]
        return c
    def test_controller_offers_only_after_click_and_never_in_games_or_file_drag(self):
        self.app.clipboard().setText(URL)
        for context,enabled,expected in [(ActivationContext((1,2),True,False),True,True),(ActivationContext((1,2),False,True),True,True),(ActivationContext((1,2)),True,False),(ActivationContext((1,2),True,False),False,False)]:
            c=self.controller();c.prefs.values['clipboard_download']=enabled
            with patch('orbitdrop.QCursor.pos',return_value=QPoint(10,10)):
                c.clipboard_click({'Shift':True},True,context);c.wheel.open_link.assert_not_called()
                c.clipboard_click({'Shift':True},False,context)
            self.assertEqual(c.wheel.open_link.called,expected)
        c=self.controller();context=ActivationContext((1,2),True,False)
        with patch('orbitdrop.QCursor.pos',return_value=QPoint(10,10)):c.clipboard_click({'Shift':True},True,context)
        with patch('orbitdrop.QCursor.pos',return_value=QPoint(60,60)):
            self.assertEqual(c.clipboard_click({'Shift':True},True,context),'drag')
            c.clipboard_click({'Shift':True},False,context)
        c.wheel.open_link.assert_not_called()
    def test_custom_convert_key_and_existing_file_take_precedence(self):
        self.app.clipboard().setText(URL);c=self.controller();c.prefs.values['convert_key']='F8';context=ActivationContext((1,2),True,False)
        with patch('orbitdrop.QCursor.pos',return_value=QPoint(10,10)):
            c.clipboard_click({'Shift':True},True,context);c.clipboard_click({'Shift':True},False,context);c.wheel.open_link.assert_not_called()
            c.clipboard_click({'F8':True},True,context);c.wheel.isVisible.return_value=True;c.wheel.files=['photo.png']
            c.clipboard_click({'F8':True},False,context);c.wheel.open_link.assert_not_called()
        self.assertEqual(self.app.clipboard().text(),URL)
    def test_real_wheel_stays_open_after_clipboard_click_and_file_drag_keeps_formats(self):
        with tempfile.TemporaryDirectory() as d:
            prefs=Preferences(d);prefs.update(dict(prefs.values,check_updates=False,check_backends=False))
            with patch('orbitdrop.QTimer.singleShot'):c=Controller(self.app,prefs)
            self.addCleanup(c.timer.stop);self.addCleanup(c.tray.hide);self.addCleanup(c.wheel.close);self.addCleanup(c.shelf.close);self.addCleanup(c.tasks.close)
            c.request_selection=Mock();c.activation_guard=Mock();c.activation_guard.context.return_value=ActivationContext((1,2),True,False)
            self.app.clipboard().setText(URL)
            def poll(codes,point):
                with patch('orbitdrop.sys.platform','win32'),patch('orbitdrop.QCursor.pos',return_value=QPoint(*point)),patch('orbitdrop.ctypes.windll',SimpleNamespace(user32=SimpleNamespace(GetAsyncKeyState=lambda code:0x8000 if code in codes else 0)),create=True):c.poll()
            poll({0x10,1},(100,100));self.assertFalse(c.wheel.isVisible())
            poll({0x10},(100,100));self.assertTrue(c.wheel.isVisible());self.assertFalse(c.wheel.automatic)
            self.assertEqual(c.wheel.labels,['download:AUDIO LADEN','download:VIDEO LADEN'])
            for i in range(35):poll(set(),(100,100))
            self.assertTrue(c.wheel.isVisible())
            c.wheel.hide();poll({1},(100,100));poll({1},(140,100));poll({0x10,1},(140,100))
            self.assertTrue(c.wheel.isVisible());self.assertTrue(c.wheel.automatic);self.assertIsNone(c.wheel.link)
            self.assertEqual(c.wheel.mode,'convert')

class WelcomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.prefs=Preferences(self.temp.name)
    def test_intro_explains_current_keys_and_optional_tools_and_saves_opt_out(self):
        self.prefs.update(dict(self.prefs.values,convert_key='F8'))
        dialog=WelcomeDialog(self.prefs);self.addCleanup(dialog.close)
        text=' '.join(label.text() for label in dialog.findChildren(QLabel))
        for word in ('F8','danach','FFmpeg','FFprobe','LibreOffice','Pandoc','optional','Python','YouTube'):
            self.assertIn(word,text)
        dialog.show();self.app.processEvents();self.assertTrue(dialog.demo.timer.isActive())
        dialog.never.setChecked(True);dialog.accept();self.assertFalse(dialog.demo.timer.isActive())
        self.assertFalse(Preferences(self.temp.name).values['show_intro'])
    def test_check_button_requests_existing_check_and_does_not_install(self):
        dialog=WelcomeDialog(self.prefs);self.addCleanup(dialog.close);callback=Mock();dialog.check_requested.connect(callback)
        dialog.show();dialog.open_check();callback.assert_called_once()
    def test_fresh_install_shows_welcome_but_not_changelog_even_after_saving(self):
        c=Controller.__new__(Controller);c.prefs=self.prefs;c.startup_existing=False;c.intro_dialog=None;c.media_status=Mock();c.help=Mock()
        with patch('changelog_ui.ChangelogDialog') as changes:
            c.show_intro();self.assertIsNotNone(c.intro_dialog)
            c.show_whats_new();changes.assert_not_called()
            c.intro_dialog.never.setChecked(True);c.intro_dialog.accept();changes.assert_not_called()
        self.assertIsNone(c.intro_dialog)
        c.show_intro();self.assertIsNone(c.intro_dialog)
        c.show_intro(force=True);self.assertIsNotNone(c.intro_dialog);c.intro_dialog.close()
    def test_settings_can_reenable_intro_and_disable_clipboard(self):
        from app_ui import SettingsDialog
        self.prefs.update(dict(self.prefs.values,show_intro=False))
        dialog=SettingsDialog(self.prefs);self.addCleanup(dialog.close)
        dialog.intro.setChecked(True);dialog.clipboard_download.setChecked(False)
        with patch('app_ui.set_autostart'):dialog.save()
        saved=Preferences(self.temp.name).values
        self.assertTrue(saved['show_intro']);self.assertFalse(saved['clipboard_download'])

if __name__=='__main__':unittest.main()
