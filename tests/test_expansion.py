import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,time,uuid,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from preferences import Preferences
from action_search import matching_actions,ActionSearchDialog
from batch_rename import plan_renames,execute_renames,validate_pairs
from workflows import run_workflow,validate_steps
from edit_models import CutModel
from pdf_pages import export_pages
from pdf_pages_ui import PdfPagesDialog
from circle_menu import direct_actions

class ExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.prefs=Preferences(self.root/'prefs')
    def wait(self,condition):
        deadline=time.monotonic()+10
        while not condition() and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        self.assertTrue(condition())
    def pdf(self):
        import pymupdf
        path=self.root/'document.pdf'
        with pymupdf.open() as pdf:
            for title in ('First','Second','Third'):pdf.new_page(width=200,height=300).insert_text((20,40),title)
            pdf.save(path)
        return path
    def test_search_filters_favorites_and_reloads_settings(self):
        actions=['format:PNG','edit:SCHNEIDEN','app:AKTIONSSUCHE','tool:UMBENENNEN']
        self.assertEqual(matching_actions(actions,'schneid',[]),['edit:SCHNEIDEN'])
        d=ActionSearchDialog(actions,self.prefs);self.addCleanup(d.close);d.query.setText('PNG');d.toggle_favorite()
        self.assertEqual(Preferences(self.prefs.root).values['favorite_actions'],['format:PNG']);d.query.clear();self.assertEqual(d.selected(),'format:PNG')
        d.only.setChecked(True);self.assertEqual(d.list.count(),1);d.run();self.assertEqual(d.chosen,'format:PNG')
    def test_search_can_inspect_new_selection_without_stale_formats(self):
        source=self.root/'image.png';Image.new('RGB',(50,40),'red').save(source)
        d=ActionSearchDialog([],self.prefs,files=[str(source)],kind='Dateiaktionen');self.addCleanup(d.close)
        self.wait(lambda:not d.jobs);self.assertIn('format:PNG',d.actions);self.assertEqual(d.kind,'Bild')
        d.files=[str(self.root/'absent.xyz')];d.inspect_files();self.wait(lambda:not d.jobs);self.assertNotIn('format:PNG',d.actions)
    def test_rename_preview_conflicts_and_windows_names(self):
        a=self.root/'one.txt';b=self.root/'two.txt';a.write_text('A');b.write_text('B')
        plans=plan_renames([a,b],'Datei_{n}',7);self.assertEqual(plans[0][1].name,'Datei_007.txt')
        existing=self.root/'Datei_007.txt';existing.write_text('Existing')
        with self.assertRaises(FileExistsError):execute_renames(plans)
        self.assertEqual(a.read_text(),'A');self.assertEqual(existing.read_text(),'Existing')
        for name in ('CON','../outside','wrong?','{name.foo}'):
            with self.subTest(name=name),self.assertRaises(ValueError):plan_renames([a],name)
    def test_rename_swaps_rollback_and_changed_source(self):
        a=self.root/'one.txt';b=self.root/'two.txt';a.write_text('A');b.write_text('B')
        plans=validate_pairs([(a,b),(b,a)]);execute_renames(plans);self.assertEqual(a.read_text(),'B');self.assertEqual(b.read_text(),'A')
        from batch_rename import move_one
        count=[0]
        def fail_once(source,target):
            count[0]+=1
            if count[0]==4:raise OSError('simulated')
            return move_one(source,target)
        plans=validate_pairs([(a,b),(b,a)])
        with patch('batch_rename.move_one',side_effect=fail_once),self.assertRaises(OSError):execute_renames(plans)
        self.assertEqual(a.read_text(),'B');self.assertEqual(b.read_text(),'A');self.assertFalse(list(self.root.glob('.orbit-rename-*')))
        plans=plan_renames([a],'{name}_{n}');a.write_text('Changed')
        with self.assertRaises(ValueError):execute_renames(plans)
    def test_workflow_runs_ordered_steps_and_keeps_original(self):
        source=self.root/'photo.png';Image.new('RGB',(200,100),'red').save(source);before=source.read_bytes()
        steps=[{'type':'resize','edge':100},{'type':'rotate','angle':90},{'type':'gray'},{'type':'compress','format':'WEBP','quality':80},{'type':'rename','pattern':'Web_{n}'}]
        output=Path(run_workflow([source],steps,{})[0]);self.assertEqual(output.name,'Web_001.webp')
        with Image.open(output) as image:self.assertEqual(image.size,(50,100));r,g,b=image.convert('RGB').getpixel((10,10));self.assertLess(max(r,g,b)-min(r,g,b),4)
        self.assertEqual(source.read_bytes(),before)
        again=Path(run_workflow([source],steps,{})[0]);self.assertNotEqual(output,again);self.assertTrue(output.exists())
    def test_workflow_failure_cleans_batch_outputs_and_strips_metadata(self):
        source=self.root/'photo.jpg';exif=Image.Exif();exif[270]='PRIVATE';Image.new('RGB',(40,30),'blue').save(source,exif=exif)
        output=Path(run_workflow([source],[{'type':'metadata'}],{})[0])
        with Image.open(output) as image:self.assertFalse(image.getexif());self.assertNotIn('exif',image.info)
        before=set(self.root.iterdir())
        with self.assertRaises(Exception):run_workflow([source,self.root/'missing.png'],[{'type':'gray'}],{})
        self.assertEqual(set(self.root.iterdir()),before)
        with self.assertRaises(ValueError):validate_steps([{'type':'rename','pattern':'{name}'},{'type':'gray'}])
    def test_saved_workflows_are_available_only_for_images(self):
        workflow={'id':str(uuid.uuid4()),'name':'Webbilder','steps':[{'type':'resize','edge':800}]}
        self.prefs.update(dict(self.prefs.values,workflows=[workflow]));loaded=Preferences(self.prefs.root).values['workflows']
        key='edit:flow:'+workflow['id'];self.assertIn(key,direct_actions([], 'Bild',[],workflows=loaded));self.assertNotIn(key,direct_actions([], 'Video',[],workflows=loaded))
    def test_pdf_duplicate_rotations_are_independent_and_source_preserved(self):
        import pymupdf
        source=self.pdf();before=source.read_bytes();entries=[{'page':2,'rotation':90},{'page':0,'rotation':0},{'page':2,'rotation':180}]
        output=export_pages(source,entries,{})[0]
        with pymupdf.open(output) as pdf:
            self.assertEqual(len(pdf),3);self.assertIn('Third',pdf[0].get_text());self.assertIn('First',pdf[1].get_text());self.assertEqual([p.rotation for p in pdf],[90,0,180])
        self.assertEqual(source.read_bytes(),before)
    def test_pdf_ui_select_rotate_duplicate_remove_undo_and_submit(self):
        calls=[];d=PdfPagesDialog(self.pdf(),lambda *args:calls.append(args));self.addCleanup(d.close);d.show();self.wait(lambda:len(d.images)==3)
        d.pages.setCurrentRow(0);d.rotate();d.duplicate();self.assertEqual(d.pages.count(),4);d.undo();self.assertEqual(d.pages.count(),3)
        d.pages.setCurrentRow(0);d.move(1);self.assertEqual(d.entries()[0]['page'],1)
        d.pages.setCurrentRow(0);d.remove();self.assertEqual(d.pages.count(),2);d.save();self.assertEqual(calls[0][0],'PDF-Seiten')
    def test_zoom_tracks_share_scale_and_editor_undo_redo(self):
        import shutil,subprocess
        if not shutil.which('ffmpeg'):self.skipTest('FFmpeg missing')
        from video_editor import VideoEditor
        path=self.root/'video.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=96x64:r=10:d=2','-c:v','libx264',str(path)],check=True)
        d=VideoEditor(path,lambda *a:None);self.addCleanup(d.close);d.show();d.activateWindow();self.wait(lambda:d.model is not None and d.frame_job is None)
        d.timeline_view.zoom.setValue(400);self.app.processEvents();self.assertGreater(d.timeline.width(),d.timeline_view.scroll.viewport().width()*3);self.assertEqual(d.timeline.width(),d.waveform.width())
        self.assertAlmostEqual(d.timeline.time_for(10+(d.timeline.width()-20)/2),1,places=5)
        d.position=1;d.add_cut();self.assertEqual(d.model.cuts,[1]);QTest.keyClick(d,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier);self.assertEqual(d.model.cuts,[]);QTest.keyClick(d,Qt.Key.Key_Y,Qt.KeyboardModifier.ControlModifier);self.assertEqual(d.model.cuts,[1])
        d.timeline.position=.8;d.timeline_view.center_playhead();self.assertGreater(d.timeline_view.scroll.horizontalScrollBar().value(),0)
    def test_rename_dialog_undo_checks_source_identity(self):
        from rename_ui import RenameDialog
        source=self.root/'original.txt';source.write_text('Original');d=RenameDialog([str(source)],self.root/'rename-state');self.addCleanup(d.close);d.pattern.setText('New_{n}');self.wait(lambda:bool(d.plans));d.apply();self.wait(lambda:d.job is None)
        target=Path(d.files[0]);self.assertEqual(target.name,'New_001.txt');self.assertTrue(d.undo.isEnabled());d.restore();self.wait(lambda:d.job is None);self.assertTrue(source.exists());self.assertFalse(target.exists())
        self.wait(lambda:bool(d.plans));d.apply();self.wait(lambda:d.job is None);target=Path(d.files[0]);target.write_text('Changed externally');d.restore();self.wait(lambda:d.job is None);self.assertIn('geändert',d.status.text());self.assertEqual(target.read_text(),'Changed externally')
    def test_cut_undo_redo_restores_marks_and_keep_flags(self):
        model=CutModel(10);model.add(2);model.add(5);model.keep(1,False);expected=model.snapshot();model.remove(0)
        self.assertTrue(model.undo());self.assertEqual(model.snapshot(),expected);self.assertTrue(model.undo());self.assertTrue(all(s[2] for s in model.segments));self.assertTrue(model.redo());self.assertFalse(model.segments[1][2]);model.add(7);self.assertFalse(model.redo())

if __name__=='__main__':unittest.main()
