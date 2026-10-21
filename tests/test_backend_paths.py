import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from filetypes import backend,windows_installed_path

class BackendPathsTests(unittest.TestCase):
    def test_pandoc_user_machine_and_winget_without_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);local=root/'local';program=root/'Program Files'
            env={'LOCALAPPDATA':str(local),'PROGRAMFILES':str(program),'PROGRAMFILES(X86)':str(root/'x86'),'PROGRAMDATA':str(root/'data')}
            for target in (local/'Pandoc/pandoc.exe',program/'Pandoc/pandoc.exe',local/'Microsoft/WinGet/Packages/JohnMacFarlane.Pandoc_test/pandoc-3/pandoc.exe'):
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b'fixture')
                with patch('filetypes.sys.platform','win32'),patch.dict(os.environ,env),patch('filetypes.shutil.which',return_value=None),patch('filetypes.windows_installed_path',return_value=None):
                    self.assertEqual(backend('pandoc'),str(target))
                target.unlink()
    def test_registry_updated_path_without_restart(self):
        class Key:
            def __enter__(self):return self
            def __exit__(self,*args):pass
        registry=SimpleNamespace(HKEY_CURRENT_USER=1,HKEY_LOCAL_MACHINE=2,OpenKey=lambda *args:Key(),QueryValueEx=lambda *args:(r'C:\FreshPandoc',1),ExpandEnvironmentStrings=lambda value:value)
        with patch.dict(sys.modules,{'winreg':registry}),patch('filetypes.shutil.which',return_value=r'C:\FreshPandoc\pandoc.exe') as which:
            self.assertEqual(windows_installed_path('pandoc'),r'C:\FreshPandoc\pandoc.exe');self.assertIn(r'C:\FreshPandoc',which.call_args.kwargs['path'])

if __name__=='__main__':unittest.main()
