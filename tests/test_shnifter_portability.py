"""Isolated filesystem/launcher regressions; no accounts, services or installs."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import ast
import csv
import json

from shnifter_paths import data_directory
from core.config import ShnifterConfig
from core.credentials import CredentialsLoader

ROOT = Path(__file__).resolve().parents[1]

class PortabilityTests(unittest.TestCase):
    def test_legacy_exporters_refuse_existing_file_without_clobber(self):
        from core.events import EventLog
        from shnifter_safe_output import atomic_write_text
        tree = ast.parse((ROOT/'Multi_Model_Trading_Bot.py').read_text(encoding='utf-8-sig'))
        exporter = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Exporter')
        namespace = {'atomic_write_text':atomic_write_text, 'io':io, 'csv':csv, 'json':json}
        exec(compile(ast.Module(body=[exporter], type_ignores=[]), '<real GUI exporter>', 'exec'), namespace)
        with tempfile.TemporaryDirectory(prefix='exports ') as folder:
            output=Path(folder)/'protected.txt'; output.write_bytes(b'original evidence')
            with self.assertRaises(FileExistsError):
                namespace['Exporter'].export_to_csv(output,[{'a':1}])
            with self.assertRaises(FileExistsError):
                namespace['Exporter'].export_to_json(output,{'a':1})
            with self.assertRaises(FileExistsError):
                EventLog.export_logs_txt(output)
            self.assertEqual(output.read_bytes(),b'original evidence')

    def test_explicit_absolute_data_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='shnifter paths ') as folder:
            path = Path(folder) / 'user state'
            with patch.dict(os.environ, {'SHNIFTER_DATA_DIR': str(path)}):
                self.assertEqual(data_directory(), path)
                self.assertFalse(path.exists())
                config = ShnifterConfig()
                config.set('ui.theme', 'isolated')
                self.assertTrue((path/'shnifter_config.json').is_file())
                self.assertEqual(ShnifterConfig().get('ui.theme'), 'isolated')

    def test_relative_data_directory_fails_clearly(self):
        with patch.dict(os.environ, {'SHNIFTER_DATA_DIR': 'relative-state'}):
            with self.assertRaisesRegex(ValueError, 'absolute'):
                data_directory()

    def test_credential_storage_uses_patched_path(self):
        from core import constants
        with tempfile.TemporaryDirectory(prefix='settings ') as folder:
            target = Path(folder)/'user_settings.json'
            with patch.object(constants, 'USER_SETTINGS_PATH', str(target)):
                CredentialsLoader.save_credentials({'synthetic': 'fixture'})
                self.assertEqual(CredentialsLoader.load_credentials(), {'synthetic':'fixture'})
                self.assertTrue(target.is_file())

    def test_setup_failure_is_failure_and_uses_interpreter_without_shell(self):
        import setup_dev_environment
        with patch('setup_dev_environment.subprocess.run', side_effect=subprocess.CalledProcessError(1, ['fixture'])) as run:
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(setup_dev_environment.main([]), 1)
            args, kwargs = run.call_args
            self.assertEqual(args[0][1:4], ['-m','pip','install'])
            self.assertEqual(kwargs['cwd'], ROOT)
            self.assertNotIn('shell', kwargs)

    @unittest.skipUnless(os.name == 'nt', 'Windows launcher test')
    def test_windows_scaffold_preserves_prototypes_from_arbitrary_cwd(self):
        with tempfile.TemporaryDirectory(prefix='shnifter launcher ') as folder:
            base=Path(folder); app=base/'project with spaces'; app.mkdir()
            frontend=app/'shnifter_frontend'; frontend.mkdir()
            protected=frontend/'shnifter_3d_visualization_popout.py'
            protected.write_bytes(b'prototype evidence\r\n')
            shutil.copy2(ROOT/'scaffold_shnifter_popouts.bat',app)
            proc=subprocess.run(['cmd','/d','/c',str(app/'scaffold_shnifter_popouts.bat')],cwd=base,capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual(protected.read_bytes(),b'prototype evidence\r\n')
            self.assertTrue((frontend/'pdf_export_popout.py').exists())
            self.assertFalse((base/'shnifter_frontend').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows launcher test')
    def test_windows_launcher_missing_environment_does_not_write_cwd(self):
        with tempfile.TemporaryDirectory(prefix='shnifter missing ') as folder:
            base=Path(folder); app=base/'project with spaces'; app.mkdir()
            shutil.copy2(ROOT/'start_shnifter.bat', app)
            proc=subprocess.run(['cmd','/d','/c',str(app/'start_shnifter.bat')],cwd=base,capture_output=True,text=True)
            self.assertEqual(proc.returncode,1)
            self.assertIn('Environment missing',proc.stderr)
            self.assertEqual(sorted(p.name for p in base.iterdir()),['project with spaces'])
