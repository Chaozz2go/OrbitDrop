import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import math
import tempfile
import time
import unittest
from pathlib import Path
from PIL import Image
from PySide6.QtCore import QPointF, QMimeData, QUrl, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication
from orbitdrop import Wheel

class WheelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.results = []
        class Target:
            pass
        target = Target()
        target.convert_files = lambda files, action: self.results.append((files, action))
        self.wheel = Wheel(target)
        self.wheel.show()
        self.app.processEvents()
        self.addCleanup(self.wheel.close)

    def test_variable_segments(self):
        for labels in [('TXT',), ('PNG', 'JPG'), ('PNG', 'JPG', 'WEBP'), ('MP4', 'WEBM', 'STANDBILD', 'MP3', 'WAV', 'FLAC')]:
            self.wheel.labels = list(labels)
            self.wheel.repaint()
            for i in range(len(labels)):
                angle = math.radians(-90 + 180/len(labels) + i*360/len(labels))
                self.assertEqual(self.wheel.segment(QPointF(190+125*math.cos(angle),190+125*math.sin(angle))), i)
            self.assertEqual(self.wheel.segment(QPointF(190,190)), -1)

    def test_page_navigation(self):
        self.wheel.all_actions = ['MP4','WEBM','MOV','MKV','AVI','WMV','GIF','STANDBILD','MP3','WAV','FLAC']
        self.wheel.display_page()
        self.assertEqual(self.wheel.labels,['MP4','WEBM','MOV','MKV','AVI','WEITER'])
        self.wheel.next_page()
        self.assertEqual(self.wheel.labels,['WMV','GIF','STANDBILD','MP3','WAV','WEITER'])
        self.wheel.next_page()
        self.assertEqual(self.wheel.labels,['FLAC','WEITER'])
        self.wheel.next_page()
        self.assertEqual(self.wheel.page,0)

    def test_drop_waits_for_content_and_uses_detected_action(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp)/'image.mp4'
            Image.new('RGB',(10,10),'blue').save(file,format='PNG')
            mime = QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(file))])
            event = QDragEnterEvent(QPointF(190,190).toPoint(), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            self.wheel.dragEnterEvent(event)
            self.assertTrue(self.wheel.checking)
            self.assertEqual(self.wheel.segment(QPointF(298,127)), -1)
            end = time.monotonic()+5
            while self.wheel.checking and time.monotonic()<end:
                self.app.processEvents()
                time.sleep(.01)
            self.assertFalse(self.wheel.checking)
            self.assertIn('format:PNG',self.wheel.labels)
            self.assertIn('edit:ZUSCHNEIDEN',self.wheel.labels)
            from direct_wheel import geometry
            point=next(entry[2] for entry in geometry(self.wheel) if entry[0]=='format:PNG')
            drop = QDropEvent(point, Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            self.wheel.dropEvent(drop)
            self.app.processEvents()
            self.assertTrue(drop.isAccepted())
            self.assertEqual(self.results, [([str(file)], 'PNG')])

if __name__ == '__main__':
    unittest.main()
