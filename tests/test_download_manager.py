import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtWidgets import QApplication
from orbitdrop import Controller
from preferences import Preferences
from menu_visibility import REMOVED_RADIAL,action_catalog,visible_actions
from circle_menu import direct_actions

class DownloadManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        prefs=Preferences(self.root/'prefs');prefs.update(dict(prefs.values,check_backends=False,check_updates=False))
        with patch('orbitdrop.QTimer.singleShot'):self.c=Controller(self.app,prefs)
        self.addCleanup(self.cleanup)
        self.pool_patch=patch.object(self.c.pool,'start');self.start=self.pool_patch.start();self.addCleanup(self.pool_patch.stop)
        self.c.download_dialog();self.m=self.c.downloader_window
    def cleanup(self):
        if self.c.downloader_window:self.c.downloader_window.stop_for_exit();self.c.downloader_window.close()
        self.c.timer.stop();self.c.tray.hide();self.c.wheel.close();self.c.shelf.close();self.c.tasks.close()
        if self.c.dashboard:self.c.dashboard.close()
    def pump(self):
        for i in range(3):self.app.processEvents()
    def queue(self,url='https://example.org/one',**kwargs):return self.m.enqueue(url,'audio',str(self.root),0,**kwargs)
    def test_tray_includes_update_check_and_removed_alt_items_stay_out(self):
        self.assertEqual([a.text() for a in self.c.tray.contextMenu().actions()],['Dashboard','Audio/Video-Downloader','Nach Updates suchen','OrbitDrop pausieren','Beenden'])
        actions=direct_actions(['file.mp4'],'Video',['MP4'],files_only=True)
        self.assertTrue(set(actions).isdisjoint(REMOVED_RADIAL));self.assertIn('tool:TERMINAL',actions);self.assertIn('app:EINSTELLUNGEN',actions)
        self.assertTrue(set(visible_actions(list(REMOVED_RADIAL),{})).isdisjoint(REMOVED_RADIAL))
        catalog={key for group,items in action_catalog({}) for key,title in items};self.assertTrue(catalog.isdisjoint(REMOVED_RADIAL))
        self.c.show_dashboard('Verwaltung');self.assertIsNotNone(self.c.dashboard.pause_keys)
    def test_collect_many_links_deduplicates_and_does_not_start_downloads(self):
        self.m.paste.setPlainText('https://example.org/a\nhttps://example.org/b\nhttps://example.org/a\ninvalid')
        self.m.collect();self.assertEqual(self.m.inbox.count(),2);self.assertIn('1 ungültige',self.m.notice.text());self.start.assert_not_called()
    def test_serial_queue_progress_and_history_without_opening_tasks(self):
        first=self.queue();second=self.queue('https://example.org/two');self.pump()
        self.assertEqual(self.m.current,first);self.assertEqual(self.start.call_count,1);self.assertFalse(self.c.tasks.isVisible())
        job=self.m.records[first]['job'];job.signals.progress.emit(35,'35 %');self.assertIn('35',self.m.records[first]['item'].text(3))
        output=self.root/'one.mp3';output.write_bytes(b'test');job.signals.done.emit([str(output)],[]);self.pump()
        self.assertEqual(self.m.records[first]['state'],'Fertig');self.assertEqual(self.m.current,second);self.assertEqual(self.start.call_count,2)
        self.assertFalse(self.c.tasks.isVisible());self.assertTrue(self.m.isVisible());self.assertTrue(self.c.prefs.history)
    def test_pause_reorder_cancel_waiting_and_retry(self):
        self.m.pause.setChecked(True);a=self.queue();b=self.queue('https://example.org/two');self.pump();self.start.assert_not_called()
        self.m.queue.setCurrentItem(self.m.records[b]['item']);self.m.move_selected(-1);self.assertEqual(self.m.waiting,[b,a])
        self.m.queue.setCurrentItem(self.m.records[a]['item']);self.m.cancel_selected();self.assertEqual(self.m.records[a]['state'],'Abgebrochen')
        self.m.pause.setChecked(False);self.pump();self.assertEqual(self.m.current,b)
        job=self.m.records[b]['job'];self.m.cancel_selected() # selected a is already canceled
        self.m.queue.setCurrentItem(self.m.records[b]['item']);self.m.cancel_selected();self.assertTrue(job.control.cancelled.is_set())
        job.was_cancelled=True;job.signals.done.emit([],[]);self.pump();self.assertIsNone(self.m.current)
        self.m.retry_selected();self.pump();self.assertIsNotNone(self.m.current);self.assertNotEqual(self.m.current,b)
    def test_close_reopen_new_link_and_playlist_selection_survive(self):
        entries=[{'url':'https://example.org/song','available':True,'title':'Song'}]
        self.m.pause.setChecked(True);key=self.queue(entries=entries);self.m.close()
        with patch.object(self.m.composer,'inspect'):
            self.c.download_dialog('https://example.org/new','video')
        self.assertIs(self.c.downloader_window,self.m);self.assertTrue(self.m.isVisible());self.assertEqual(self.m.composer.url.text(),'https://example.org/new')
        self.assertEqual(self.m.records[key]['request']['entries'],entries);self.assertEqual(self.m.composer.mode.currentData(),'video')
    def test_immediate_worker_completion_is_observed_before_start_returns(self):
        self.start.side_effect=lambda job:job.signals.done.emit([],['Simulated failure'])
        key=self.queue();self.pump();self.assertEqual(self.m.records[key]['state'],'Fehler');self.assertIsNone(self.m.current)
        self.assertEqual(self.c.jobs,set());self.assertFalse(self.c.tasks.has_running())
    def test_queue_cancel_on_exit_and_completed_files_are_preserved(self):
        key=self.queue();self.queue('https://example.org/two');self.pump();job=self.m.records[key]['job']
        output=self.root/'done.mp3';output.write_bytes(b'finished')
        self.m.stop_for_exit();self.assertTrue(job.control.cancelled.is_set());job.was_cancelled=True;job.signals.done.emit([str(output)],[]);self.pump()
        self.assertTrue(output.exists());self.assertIsNone(self.m.current);self.assertFalse(self.m.has_pending());self.assertEqual(self.start.call_count,1)
    def test_duplicate_active_request_is_rejected_but_other_format_is_allowed(self):
        self.m.pause.setChecked(True);self.queue()
        with self.assertRaisesRegex(ValueError,'bereits'):self.queue()
        self.m.enqueue('https://example.org/one','video',str(self.root),0)
        self.assertEqual(len(self.m.waiting),2)
    def test_composer_submission_keeps_editor_open_and_invalid_input_does_not_queue(self):
        self.m.composer.accept();self.assertTrue(self.m.isVisible());self.assertFalse(self.m.composer.closed)
        with self.assertRaises(ValueError):self.queue('not a link')
        with self.assertRaises(ValueError):self.queue(entries=[])
        self.assertEqual(self.m.records,{})

if __name__=='__main__':unittest.main()
