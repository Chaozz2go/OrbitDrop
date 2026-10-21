"""Catch project modules that shadow stdlib packages in newer Python versions."""
import os,subprocess,sys,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class StartupImportTests(unittest.TestCase):
    def test_project_names_do_not_shadow_stdlib(self):
        # compression is the stdlib package used by gzip in the reported Python 3.15 traceback.
        reserved=set(sys.stdlib_module_names)|{'compression'}
        self.assertFalse({p.stem for p in ROOT.glob('*.py')}&reserved)
    def test_newer_stdlib_compression_package_remains_importable(self):
        with tempfile.TemporaryDirectory() as temp:
            package=Path(temp)/'compression';package.mkdir();(package/'__init__.py').write_text('');(package/'_common.py').write_text('marker = "stdlib"\n')
            env=dict(os.environ,PYTHONPATH=temp)
            result=subprocess.run([sys.executable,'-c','from compression._common import marker; assert marker == "stdlib"; import gzip; import orbitdrop; assert gzip.decompress(gzip.compress(b"OrbitDrop")) == b"OrbitDrop"; print("ok")'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
