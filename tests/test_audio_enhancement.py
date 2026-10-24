import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import math,tempfile,time,wave,shutil,json
from pathlib import Path
from array import array
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication,QInputDialog,QMessageBox
from PySide6.QtCore import QTimer,QUrl
from audio_tools import audio_settings,improve_audio
from audio_dsp import effect_filters,require_filters,parse_filter_names
from audio_profiles import FACTORY,factory_profile,AudioProfileStore
from audio_preview import build_preview,matched_gains,pcm_stats,preview_settings,preview_key
from audio_tools_ui import AudioToolsDialog
from task_runtime import TaskControl,Cancelled

class AudioEnhancementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def tone(self,name='source.wav',frequency=1000,duration=2,amplitude=.1,channels=1):
        path=self.root/name;rate=16000;values=array('h')
        for n in range(round(duration*rate)):
            level=amplitude(n/rate) if callable(amplitude) else amplitude
            sample=round(32767*level*math.sin(2*math.pi*frequency*n/rate));values.extend([sample]*channels)
        with wave.open(str(path),'wb') as wav:wav.setnchannels(channels);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes(values.tobytes())
        return path
    def wait(self,condition,limit=15):
        end=time.monotonic()+limit
        while not condition() and time.monotonic()<end:self.app.processEvents();time.sleep(.01)
        self.assertTrue(condition())
    def dialog(self,source):
        d=AudioToolsDialog([source],lambda *args:None,SimpleNamespace(root=self.root/'state'));self.addCleanup(d.reject);d.show();self.wait(lambda:d.probe_job is None);return d
    def test_values_and_filter_parameters_are_validated_and_no_op_is_preserved(self):
        for values in ({'eq':[0]*9},{'eq':[13]*10},{'strength':float('nan')},{'comp_ratio':100},{'deess_intensity':2},{'peak':0},{'highpass':-1}):
            with self.subTest(values=values),self.assertRaises(ValueError):audio_settings(values)
        with self.assertRaises(ValueError):audio_settings({'normalize':False})
        p=audio_settings({**factory_profile('radio'),'strength':0});self.assertEqual(effect_filters(p),[])
        self.assertEqual(audio_settings({**factory_profile('podcast'),'normalize':False})['normalize'],False)
    def test_profiles_are_independent_of_loudness_and_do_not_share_mutable_eq(self):
        first=factory_profile('podcast');first['eq'][0]=12;self.assertEqual(factory_profile('podcast')['eq'][0],0)
        for identifier,name,hint,values in FACTORY:
            p=factory_profile(identifier);self.assertNotIn('lufs',p);self.assertEqual(len(p['eq']),10)
        music=factory_profile('music');self.assertFalse(music['compressor']);self.assertFalse(music['deesser']);self.assertEqual(music['highpass'],0)
    def test_personal_profiles_persist_unicode_and_fail_closed_on_corruption(self):
        store=AudioProfileStore(self.root/'state');identifier=store.add('Meine Stimme ä',factory_profile('warm'));again=AudioProfileStore(store.root);self.assertEqual(again.items[0]['id'],identifier);self.assertEqual(again.items[0]['name'],'Meine Stimme ä')
        with self.assertRaises(ValueError):again.add('Meine Stimme ä',factory_profile('radio'))
        again.remove(identifier);self.assertEqual(AudioProfileStore(store.root).items,[])
        again.path.write_text('{broken',encoding='utf-8');before=again.path.read_bytes();broken=AudioProfileStore(store.root)
        with self.assertRaises(ValueError):broken.add('Another',factory_profile('music'))
        self.assertEqual(broken.path.read_bytes(),before)
    def test_filter_lists_accept_build_flag_variations_and_both_streams(self):
        text='Filters:\n T.. equalizer A->A Equalize\n TS.C acompressor A->A Compress\n .. loudnorm A->A Normalize\n aresample A->A Resample\n ... anullsrc |->A Source\n'
        expected={'equalizer','acompressor','loudnorm','aresample','anullsrc'};self.assertEqual(parse_filter_names(text),expected)
        from audio_dsp import _filter_names
        _filter_names.cache_clear()
        try:
            with patch('audio_dsp.run',return_value=SimpleNamespace(returncode=0,stdout='',stderr=text)):
                self.assertEqual(_filter_names('filter-list-test',0,0),expected)
        finally:_filter_names.cache_clear()
    def test_missing_filter_is_explained_before_any_output(self):
        p=audio_settings({**factory_profile('radio'),'protect':True})
        with patch('audio_dsp._filter_names',return_value={'asetpts','aresample','atrim','loudnorm'}),self.assertRaisesRegex(ValueError,'acompressor'):require_filters(p)
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_all_factory_profiles_render_valid_audio_and_preserve_source(self):
        source=self.tone();before=source.read_bytes()
        for identifier,name,hint,values in FACTORY:
            result=build_preview(source,{**factory_profile(identifier),'normalize':True,'protect':True},0,1)
            try:
                self.assertAlmostEqual(result.duration,1,delta=.02);stats=pcm_stats(result.after);self.assertGreater(stats['rms'],0);self.assertLess(stats['peak'],.91)
            finally:result.cleanup()
        self.assertEqual(source.read_bytes(),before)
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_eq_gain_is_audible_and_preview_source_duration_is_preserved(self):
        source=self.tone(amplitude=.05);eq=[0]*10;eq[5]=6
        result=build_preview(source,{'normalize':False,'eq_enabled':True,'eq':eq},0,1.5)
        try:
            ratio=result.after_rms/result.before_rms;self.assertGreater(ratio,1.85);self.assertLess(ratio,2.1)
            with wave.open(str(result.after),'rb') as wav:self.assertEqual(wav.getnchannels(),1);self.assertEqual(wav.getframerate(),48000)
            self.assertEqual(preview_key(source,{'normalize':False,'eq_enabled':True,'eq':eq},0,1.5),result.key)
        finally:root=result.root;result.cleanup()
        self.assertFalse(root.exists())
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_compressor_reduces_loud_quiet_difference(self):
        source=self.tone(duration=3,amplitude=lambda t:.04 if t<1.5 else .7)
        result=build_preview(source,{'normalize':False,'compressor':True,'comp_ratio':4,'comp_threshold':-25},0,3)
        def rms(path,start,frames):
            with wave.open(str(path),'rb') as wav:wav.setpos(round(start*48000));values=array('h');values.frombytes(wav.readframes(frames));return math.sqrt(sum(v*v for v in values)/len(values))
        try:
            original=rms(result.before,2,24000)/rms(result.before,.5,24000);processed=rms(result.after,2,24000)/rms(result.after,.5,24000);self.assertLess(processed,original*.5)
        finally:result.cleanup()
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_deesser_reduces_high_frequency_sibilance_more_than_voice_body(self):
        ratios=[]
        for frequency in (1000,6000):
            source=self.tone(name=f'tone-{frequency}.wav',frequency=frequency)
            result=build_preview(source,{'normalize':False,'deesser':True,'deess_intensity':.8,'deess_amount':.8},0,1)
            try:ratios.append(result.after_rms/result.before_rms)
            finally:result.cleanup()
        self.assertGreater(ratios[0],.9);self.assertLess(ratios[1],.7)
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_changed_source_rejects_preview_and_removes_export(self):
        source=self.tone();roots=[]
        import audio_preview,audio_tools
        preview_render=audio_preview.render_audio
        def mutate_preview(*args,**kwargs):
            result=preview_render(*args,**kwargs);roots.append(Path(args[1]).parent);source.write_bytes(source.read_bytes()+b'changed');return result
        with patch('audio_preview.render_audio',side_effect=mutate_preview),self.assertRaisesRegex(ValueError,'geändert'):build_preview(source,{'normalize':True},0,1)
        self.assertTrue(roots);self.assertFalse(roots[0].exists())
        full_render=audio_tools.render_audio;before=set(self.root.iterdir())
        def mutate_export(*args,**kwargs):
            result=full_render(*args,**kwargs);source.write_bytes(source.read_bytes()+b'changed again');return result
        with patch('audio_tools.render_audio',side_effect=mutate_export),self.assertRaisesRegex(ValueError,'geändert'):improve_audio([source],{'normalize':False,'protect':True},{})
        self.assertEqual(set(self.root.iterdir()),before)
    def test_matching_only_attenuates_and_changes_no_export_settings(self):
        self.assertEqual(matched_gains(.1,.5),(1.,.2));self.assertEqual(matched_gains(0,.5),(1.,1.))
        p=audio_settings({**factory_profile('radio'),'trim':True,'fade_in':1,'fade_out':2,'format':'MP3'});preview=preview_settings(p);self.assertFalse(preview['trim']);self.assertEqual(preview['fade_in'],0);self.assertEqual(p['fade_in'],1);self.assertEqual(p['format'],'MP3');self.assertEqual(preview['eq'],p['eq'])
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_cancel_cleans_preview_and_partial_export(self):
        source=self.tone();before=set(self.root.iterdir());control=TaskControl();control.cancel()
        with control.activate(),self.assertRaises(Cancelled):build_preview(source,{'normalize':True},0,1)
        self.assertEqual(set(self.root.iterdir()),before)
        def cancel(percent,message):
            if message=='Audiodatei wird berechnet …':control.cancel()
        control=TaskControl(cancel)
        with control.activate(),self.assertRaises(Cancelled):improve_audio([source],{'normalize':False,'protect':True},{})
        self.assertEqual(set(self.root.iterdir()),before)
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_ui_profiles_controls_preview_matching_and_cached_reuse(self):
        source=self.tone();d=self.dialog(source);self.assertEqual(d.profile.currentData(),'podcast');d.lufs.setValue(-23);d.profile.setCurrentIndex(d.profile.findData('radio'));self.assertEqual(d.lufs.value(),-23);self.assertEqual(d.parameters()['comp_ratio'],3.2)
        previous=d.eq[7].value();d.quick[2].setValue(d.quick[2].value()+1);self.assertGreater(d.eq[7].value(),previous);self.assertFalse(d.scroll.isVisible());d.expand.setChecked(True);self.assertTrue(d.scroll.isVisible())
        d.request_preview();self.wait(lambda:d.preview_job is None);self.assertIsNotNone(d.preview);self.assertTrue(d.play.isEnabled());original=d.preview
        d.request_preview();self.assertIs(d.preview,original);self.assertIsNone(d.preview_job)
        expected=matched_gains(d.preview.before_rms,d.preview.after_rms);self.assertAlmostEqual(d.outputs[1].volume(),.8*expected[1],places=5);d.match.setChecked(False);self.assertAlmostEqual(d.outputs[1].volume(),.8,places=5)
        d.select_audio(0);self.assertEqual(d.current,0);self.assertTrue(d.before_button.isChecked());d.reject();self.assertTrue(d.closed);self.wait(lambda:not original.root.exists())
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_ui_profile_save_reload_and_export_parameters(self):
        source=self.tone();d=self.dialog(source);d.comp_ratio.setValue(3.5)
        with patch.object(QInputDialog,'getText',return_value=('Mein Profil',True)):d.save_own()
        self.assertTrue(d.profile.currentData().startswith('custom:'));d.reject()
        again=self.dialog(source);idx=next(i for i in range(again.profile.count()) if again.profile.itemText(i)=='Eigenes · Mein Profil');again.profile.setCurrentIndex(idx);self.assertEqual(again.comp_ratio.value(),3.5)
        calls=[];again.submit=lambda *args:calls.append(args);again.save();self.assertEqual(calls[0][0],'Audio verbessern');self.assertEqual(calls[0][2]['comp_ratio'],3.5);self.assertTrue(again.closed)
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_modal_close_exits_and_pending_preview_is_discarded(self):
        source=self.tone();d=self.dialog(source);timeouts=[];guard=QTimer();guard.setSingleShot(True);guard.timeout.connect(lambda:(timeouts.append(True),d.done(0)));guard.start(3000);QTimer.singleShot(50,d.reject);d.exec();guard.stop();self.assertFalse(timeouts);self.assertTrue(d.closed)
        other=self.dialog(source);other.request_preview();other.reject();self.wait(lambda:not other.jobs);self.assertIsNone(other.preview)

if __name__=='__main__':unittest.main()
