import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import tempfile
import time
from PIL import Image
import unittest
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication
from orbitdrop import Controller, Wheel
from preferences import Preferences
from app_version import VERSION
from changelog import local_entries, notes_for, resource_path
from changelog_ui import ChangelogDialog
from help_ui import HelpDialog
from update_ui import UpdateDialog


class HelpDocumentParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.images = []; self.ids = set(); self.targets = []
    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if 'id' in data: self.ids.add(data['id'])
        if tag == 'img': self.images.append(data.get('src', ''))
        if tag == 'a' and data.get('href', '').startswith('#'): self.targets.append(data['href'][1:])


class ReleaseHelpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.prefs = Preferences(self.root / 'prefs')

    def test_installed_history_exists_and_search_works_without_network(self):
        with patch('requests.get', side_effect=AssertionError('No network allowed')):
            records = local_entries()
            self.assertEqual(records[0]['version'], VERSION)
            self.assertIn('## '+VERSION, notes_for(VERSION))
            self.assertIn('0.20.0', [record['version'] for record in records])
            dialog = ChangelogDialog(); self.addCleanup(dialog.close)
            self.assertIn(VERSION, dialog.text.toPlainText())
            dialog.query.setText('Spielschutz'); self.assertIn('Spielschutz', dialog.text.toPlainText())
            dialog.query.setText('not_in_this_history_123'); self.assertIn('Keine passenden', dialog.text.toPlainText())

    def test_release_notes_match_current_history(self):
        expected = 'OrbitDrop ' + VERSION + '\n\n' + notes_for(VERSION)
        self.assertEqual(resource_path('release-notes.md').read_text(encoding='utf-8'), expected)

    def test_update_error_keeps_local_changes_visible_and_new_release_notes_replace_them(self):
        with patch('update_ui.QTimer.singleShot'), patch('requests.get', side_effect=OSError('offline')):
            dialog = UpdateDialog(self.prefs, Mock()); self.addCleanup(dialog.close)
            original = dialog.notes.toPlainText(); self.assertIn(VERSION, original)
            dialog.downloading = False; dialog.ready(None, 'Keine Internetverbindung')
            self.assertEqual(dialog.notes.toPlainText(), original)
            self.assertFalse(dialog.download_button.isEnabled())
            dialog.ready({'version': '9.0.0', 'newer': True, 'notes': 'Neu: Testfunktion'}, '')
            self.assertIn('Testfunktion', dialog.notes.toPlainText()); self.assertTrue(dialog.download_button.isEnabled())

    def test_handbook_is_self_contained_and_all_local_navigation_targets_exist(self):
        document = resource_path('docs/OrbitDrop-Handbuch.html').read_text(encoding='utf-8')
        parser = HelpDocumentParser(); parser.feed(document)
        self.assertGreaterEqual(len(parser.images), 3)
        self.assertTrue(all(source.startswith('data:image/png;base64,') for source in parser.images))
        self.assertTrue(set(parser.targets) <= parser.ids)
        for phrase in ('Content-Security-Policy', 'Beispiele Schritt für Schritt', 'Alle Formate &amp; Grenzen', VERSION, 'query'):
            self.assertIn(phrase, document)
        self.assertNotIn('<script src=', document)

    def test_handbook_save_and_help_search_do_not_require_network(self):
        target = self.root / 'handbook.html'
        with patch('requests.get', side_effect=AssertionError('No network allowed')):
            dialog = HelpDialog(self.prefs); self.addCleanup(dialog.close)
            dialog.query.setText('unerwünschten'); self.assertIn('C drücken', dialog.browser.toPlainText().replace('C\n', 'C '))
            with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(target), 'HTML-Datei')):
                dialog.save_manual()
            self.assertEqual(target.read_bytes(), resource_path('docs/OrbitDrop-Handbuch.html').read_bytes())

    def test_automatic_direct_roots_have_no_back_but_manual_navigation_does(self):
        image=self.root/'image.png';Image.new('RGB',(20,20),'red').save(image)
        wheel = Wheel(SimpleNamespace(prefs=self.prefs)); self.addCleanup(wheel.close)
        for mode in ('convert', 'edit', 'files'):
            wheel.open(automatic=True, mode=mode)
            self.assertFalse(any(key.endswith(':ZURÜCK') for key in wheel.labels))
            wheel.files = [str(image)]; wheel.kind = 'Bild'; wheel.formats = ['PNG']; wheel.display_mode()
            self.assertFalse(any(key.endswith(':ZURÜCK') for key in wheel.labels))
        wheel.navigate('home'); wheel.select_action('BEARBEITEN')
        self.assertIn('edit:ZURÜCK', wheel.labels)
        wheel.display_mode(); self.assertIn('edit:ZURÜCK', wheel.labels)
        wheel.select_action('edit:ZURÜCK'); self.assertEqual(wheel.mode, 'home'); self.assertEqual(wheel.files, [str(image)])
        wheel.switch_mode('convert')
        deadline=time.monotonic()+5
        while wheel.checking and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        self.assertIn('format:PNG', wheel.labels)
        self.assertNotIn('format:ZURÜCK', wheel.labels)

    def test_upgrade_from_history_only_installation_also_shows_changes(self):
        self.prefs.record('Konvertierung',[],[],'Fertig')
        c=Controller.__new__(Controller);c.prefs=self.prefs
        with patch('changelog_ui.ChangelogDialog') as dialog:
            c.show_whats_new();dialog.assert_called_once_with(previous=None)
            c.show_whats_new();dialog.assert_called_once()

    def test_new_version_shown_once_and_fresh_install_is_not_interrupted(self):
        c = Controller.__new__(Controller); c.prefs = self.prefs
        with patch('changelog_ui.ChangelogDialog') as dialog:
            c.show_whats_new(); dialog.assert_not_called()
            self.assertEqual(Preferences(self.prefs.root).values['seen_version'], VERSION)
            c.show_whats_new(); dialog.assert_not_called()
            self.prefs.update(dict(self.prefs.values, seen_version='0.20.0'))
            c.show_whats_new(); dialog.assert_called_once_with(previous='0.20.0')
            c.show_whats_new(); dialog.assert_called_once()


if __name__ == '__main__': unittest.main()
