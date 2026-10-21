"""Closed Python/Qt widget cycles must not be collected by preview workers."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import gc,threading,unittest,weakref
from PySide6.QtWidgets import QApplication,QWidget
from ui_theme import ensure_gui_lifetimes

class UiLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_worker_allocations_leave_closed_widgets_for_gui_collection(self):
        ensure_gui_lifetimes();self.assertFalse(gc.isenabled());destroyed=[];gui_thread=threading.get_ident()
        def closed_window():
            window=QWidget();window.cycle=window;window.destroyed.connect(lambda:destroyed.append(threading.get_ident()));window.close()
            return weakref.ref(window)
        reference=closed_window()
        def allocate():
            for _ in range(gc.get_threshold()[0]+100):
                cycle=[];cycle.append(cycle)
        worker=threading.Thread(target=allocate);worker.start();worker.join()
        self.assertIsNotNone(reference());self.assertEqual(destroyed,[])
        self.app._orbit_gc.collect_if_needed()
        self.assertIsNone(reference());self.assertEqual(destroyed,[gui_thread])

if __name__=='__main__':unittest.main()
