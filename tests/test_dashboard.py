import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import ast,hashlib,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication
from orbitdrop import Controller,SetupJob
from preferences import Preferences
from setup_tools import check_tools,office_probe,winget_command,install_tool,TOOLS

ROOT=Path(__file__).resolve().parents[1]

class SetupTests(unittest.TestCase):
    def test_office_probe_never_launches_windows_gui_for_version(self):
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/'soffice.exe';exe.touch()
            self.assertIsNone(office_probe(str(exe),'win32'))
            console=exe.with_suffix('.com');console.touch()
            self.assertEqual(office_probe(str(exe),'win32'),[str(console),'--headless','--version'])
    def test_quiet_readiness_check_has_per_feature_results_and_no_network(self):
        with patch('setup_tools.backend',return_value='/tool'),patch('extended.soffice',return_value='/office'),patch('setup_tools.office_probe',return_value=None),patch('ocr_data.find_tessdata',return_value=Path('/tessdata')),patch('setup_tools.run',return_value=SimpleNamespace(returncode=0,stdout='1.0\n',stderr='')) as run:
            rows=check_tools('/state')
        self.assertEqual({r['id'] for r in rows},set(TOOLS));self.assertTrue(all(r['ready'] for r in rows))
        self.assertFalse(any(call.args[0][0]=='/office' for call in run.call_args_list))
        with patch('setup_tools.backend',return_value=None),patch('extended.soffice',return_value=None),patch('ocr_data.find_tessdata',return_value=None):
            rows=check_tools('/state')
        self.assertTrue(all(not row['ready'] for row in rows))
    def test_install_commands_are_fixed_and_never_disable_hash_checks(self):
        with patch('setup_tools.sys.platform','win32'),patch('setup_tools.shutil.which',return_value='winget.exe'):
            command=winget_command('office')
            self.assertEqual(command[:4],['winget.exe','install','--id','TheDocumentFoundation.LibreOffice'])
            for flag in ('--exact','--silent','--disable-interactivity','--accept-package-agreements'):self.assertIn(flag,command)
            self.assertNotIn('--ignore-security-hash',command)
            with self.assertRaises(ValueError):winget_command('injected')
        with patch('setup_tools.sys.platform','win32'),patch('setup_tools.shutil.which',return_value=None):
            with self.assertRaisesRegex(OSError,'Downloadseite'):winget_command('pandoc')
    def test_install_ocr_uses_user_state_and_failures_are_reported(self):
        with patch('ocr_data.install_languages',return_value=Path('/state/tessdata')) as install:
            self.assertEqual(install_tool('ocr','/state'),str(Path('/state/tessdata')));install.assert_called_once_with(Path('/state/tessdata'))
        with patch('setup_tools.winget_command',return_value=['winget']),patch('setup_tools.run',return_value=SimpleNamespace(returncode=1,stderr='Denied',stdout='')):
            with self.assertRaisesRegex(OSError,'Denied'):install_tool('office','/state')

class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.prefs=Preferences(self.temp.name)
        self.prefs.update(dict(self.prefs.values,check_backends=False,check_updates=False))
        with patch('orbitdrop.QTimer.singleShot'):self.c=Controller(self.app,self.prefs)
        self.addCleanup(self.cleanup)
    def cleanup(self):
        self.c.timer.stop();self.c.tray.hide();self.c.wheel.close();self.c.shelf.close();self.c.tasks.close()
        if self.c.dashboard:self.c.dashboard.close()
    def test_hidden_dashboard_pages_are_built_only_when_requested(self):
        self.c.show_dashboard();d=self.c.dashboard
        self.assertIsNone(d._guide);self.assertIsNone(d._settings_panel);self.assertIsNone(d._updates_panel)
        self.c.update_checked({'notes':'Background notes','version':'99.0.0','newer':False},'')
        self.assertIsNone(d._updates_panel)
        d.open_page('Updates');self.assertEqual(d.updates_panel.notes.toPlainText(),'Background notes')
        d.open_page('Einstellungen');self.assertIsNotNone(d._settings_panel);self.assertIsNone(d._guide)
        settings=d.settings_panel;d.open_page('Willkommen');d.open_page('Einstellungen');self.assertIs(d.settings_panel,settings)
        d.open_page('Anleitung');self.assertIsNotNone(d._guide)
    def test_modeless_persistent_dashboard_reopens_and_callbacks_do_not_close_it(self):
        self.c.show_dashboard();d=self.c.dashboard
        self.assertTrue(d.isVisible());self.assertIsNone(self.app.activeModalWidget())
        self.c.show_dashboard('Einrichtung');self.assertIs(self.c.dashboard,d);self.assertEqual(d.pages.currentIndex(),1)
        self.c.backends_checked([{'id':key,'ready':True,'detail':'Ready'} for key in TOOLS],[])
        self.assertTrue(d.isVisible());self.assertIn('5 von 5',d.home_status.text())
        self.c.help();self.assertEqual(d.pages.currentIndex(),2);self.assertTrue(d.isVisible())
        self.c.settings();self.assertEqual(d.pages.currentIndex(),3);self.assertTrue(d.isVisible())
        d.close();self.assertFalse(d.isVisible())
        self.c.backends_checked([],[]);self.assertFalse(d.isVisible())
        self.c.show_dashboard();self.assertIs(self.c.dashboard,d);self.assertTrue(d.isVisible())
    def test_embedded_settings_save_and_update_guide_and_start_choice(self):
        self.c.show_dashboard('Einstellungen');d=self.c.dashboard;p=d.settings_panel
        p.convert.setCurrentText('F8');p.dashboard_start.setChecked(False)
        with patch('app_ui.set_autostart'):p.save()
        self.assertTrue(d.isVisible());self.assertTrue(p.isVisible());self.assertIn('F8',d.keys.text())
        self.assertFalse(Preferences(self.temp.name).values['show_dashboard']);self.assertFalse(d.at_start.isChecked())
        d.at_start.setChecked(True);self.assertTrue(Preferences(self.temp.name).values['show_dashboard'])
    def test_setup_explicit_single_job_and_error_stays_in_dashboard(self):
        self.c.show_dashboard('Einrichtung');d=self.c.dashboard
        with patch.object(self.c.pool,'start') as start:
            self.c.setup_tool('office');job=self.c.setup_job
            self.assertIsInstance(job,SetupJob);start.assert_called_once()
            self.c.setup_tool('pandoc');start.assert_called_once()
            self.c.cancel_setup();self.assertTrue(job.control.cancelled.is_set())
            job.was_cancelled=True;self.c.setup_finished(job,[],[])
        self.assertIsNone(self.c.setup_job);self.assertTrue(d.isVisible());self.assertIn('abgebrochen',d.status.text());self.assertTrue(d.check.isEnabled())
    def test_long_installer_errors_stay_in_details_without_expanding_footer(self):
        self.c.show_dashboard('Einrichtung');d=self.c.dashboard;d.setup_started('office')
        d.setup_finished('Installer error: '+('technical details '*300))
        self.assertLess(len(d.status.text()),160);self.assertIn('technical details',d.tool_rows['office']['detail'].toPlainText());self.assertTrue(d.isVisible())
    def test_tray_dashboard_and_start_scheduling_and_polling_remain_v20(self):
        self.assertEqual([a.text() for a in self.c.tray.contextMenu().actions()],['Dashboard','Audio/Video-Downloader','OrbitDrop pausieren','Beenden']);self.assertEqual(self.c.timer.interval(),25)
        for enabled in (True,False):
            self.prefs.update(dict(self.prefs.values,show_dashboard=enabled))
            with patch('orbitdrop.QTimer.singleShot') as timer:
                c=Controller(self.app,self.prefs)
            try:self.assertEqual(sum(call.args[0]==100 for call in timer.call_args_list),int(enabled))
            finally:c.timer.stop();c.tray.hide();c.wheel.close();c.shelf.close();c.tasks.close()
    def test_pause_is_synchronized_between_tray_and_dashboard(self):
        self.c.pause_action.setChecked(True)
        self.assertTrue(self.c.shortcuts_paused)
        self.c.show_dashboard('Verwaltung');d=self.c.dashboard
        self.assertTrue(d.pause_keys.isChecked())
        d.pause_keys.setChecked(False)
        self.assertFalse(self.c.shortcuts_paused);self.assertFalse(self.c.pause_action.isChecked())
        self.c.pause_action.setChecked(True);self.assertTrue(d.pause_keys.isChecked())

    def test_updates_embedded_without_unrequested_network_or_modal(self):
        with patch('update_ui.QThreadPool.globalInstance') as pool:
            self.c.show_dashboard('Updates');d=self.c.dashboard;p=d.updates_panel
            self.app.processEvents();pool.return_value.start.assert_not_called()
            self.assertTrue(p.isVisible());self.assertIsNone(self.app.activeModalWidget())
            self.c.updates();pool.return_value.start.assert_called_once()
            self.c.updates();pool.return_value.start.assert_called_once()
            p.ready({'notes':'Release notes','version':'99.0.0','newer':True},'')
            self.assertIn('99.0.0',p.status.text());self.assertTrue(p.download_button.isEnabled())
            p.reject();self.assertTrue(d.isVisible());self.assertFalse(p.stopped.is_set())
            self.c.show_dashboard('Updates');self.assertIn('Release notes',p.notes.toPlainText())
            p.auto.setChecked(True);self.assertTrue(d.settings_panel.updates.isChecked())
            self.assertTrue(self.prefs.values['check_updates'])

    def test_startup_update_result_reaches_dashboard_and_error_is_readable(self):
        self.c.show_dashboard('Updates');p=self.c.dashboard.updates_panel
        self.c.update_checked({'notes':'Ready','version':'99.0.0','newer':False},'')
        self.assertEqual(p.notes.toPlainText(),'Ready')
        self.c.update_checked(None,'Offline');self.assertEqual(p.status.text(),'Offline')
        p.installer=Path('downloaded.exe')
        self.c.update_checked(None,'Late check');self.assertEqual(p.status.text(),'Offline')

    def test_radial_painting_files_are_exact_v20_sources(self):
        # Freeze the release sources: this feature must not restyle or reposition the wheel.
        hashes={'direct_wheel.py':'072bf7f90bc831e3f623538fb79042dcbaafe65e','wheel_render.py':'7a34d74fb70d149d3d05d4ce2b6b62c0a31b2d70','radial_style.py':'fca5ca825c5a6ac7e9dd8d5a4ab3ac7df7ea6ae7'}
        for name,expected in hashes.items():
            b=(ROOT/name).read_text(encoding='utf-8').encode('utf-8');actual=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest();self.assertEqual(actual,expected,name)

    def test_wheel_is_unchanged_from_v20(self):
        tree=ast.parse((ROOT/'orbitdrop.py').read_text(encoding='utf-8'));classes={x.name:x for x in tree.body if isinstance(x,ast.ClassDef)}
        wheel=hashlib.sha256(ast.dump(classes['Wheel']).encode()).hexdigest()
        self.assertEqual(wheel,'ea5e94bc0369906fef49c3bcc13a2dfe16df4827eac5737598b8180ae4028b2c')

if __name__=='__main__':unittest.main()
