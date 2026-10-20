"""Focused runner preflight must never turn missing/zero/failed tests into PASS."""
import importlib.util
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'tools' / 'run_shnifter_focused_tests.py'
spec = importlib.util.spec_from_file_location('focused_runner', PATH)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / 'results'

    def fake_run(self, count=5, failures=0, skipped=0, code=0):
        def run(cmd, **kw):
            path = Path(next(arg.split('=', 1)[1] for arg in cmd if arg.startswith('--junitxml=')))
            path.write_text(f'<testsuites><testsuite tests="{count}" failures="{failures}" errors="0" skipped="{skipped}"/></testsuites>')
            return types.SimpleNamespace(returncode=code, stdout='test fixture', stderr='')
        return run

    def test_actual_result_receipt_contains_hashes_and_scope(self):
        with patch.object(runner.subprocess, 'run', side_effect=self.fake_run()):
            self.assertEqual(runner.main(['--suite', 'lifecycle', '--output-dir', str(self.output)]), 0)
        receipt = json.loads((self.output / 'receipt.json').read_text())
        self.assertFalse(receipt['full_repository_suite'])
        self.assertFalse(receipt['live_authorized'])
        self.assertTrue(receipt['sources']['shnifter_order_events.py']['sha256'])

    def test_zero_tests_are_not_success(self):
        with patch.object(runner.subprocess, 'run', side_effect=self.fake_run(count=0)):
            self.assertEqual(runner.main(['--suite', 'lifecycle', '--output-dir', str(self.output)]), 1)

    def test_test_failures_are_not_success(self):
        with patch.object(runner.subprocess, 'run', side_effect=self.fake_run(failures=1, code=1)):
            self.assertEqual(runner.main(['--suite', 'lifecycle', '--output-dir', str(self.output)]), 1)

    def test_skips_do_not_count_as_full_pass(self):
        with patch.object(runner.subprocess, 'run', side_effect=self.fake_run(skipped=1)):
            self.assertEqual(runner.main(['--suite', 'lifecycle', '--output-dir', str(self.output)]), 1)

    def test_source_mismatch_stops_before_test_launch(self):
        manifest = self.root / 'expected.json'
        manifest.write_text(json.dumps({'sources': {'shnifter_order_events.py': {'sha256': '0' * 64}}}))
        with patch.object(runner.subprocess, 'run') as process:
            self.assertEqual(runner.main(['--suite', 'lifecycle', '--output-dir', str(self.output),
                                          '--expected-manifest', str(manifest)]), 1)
            process.assert_not_called()
        self.assertIn('source differs', (self.output / 'receipt.json').read_text())

    def test_missing_selected_test_stops_before_launch(self):
        with patch.dict(runner.SUITES, {'lifecycle': ['nonexistent_test.py']}):
            with patch.object(runner.subprocess, 'run') as process:
                self.assertEqual(runner.main(['--suite', 'lifecycle', '--output-dir', str(self.output)]), 1)
                process.assert_not_called()

    def test_source_change_during_tests_cannot_pass(self):
        before = {"sample.py": {"sha256": "aaa"}}
        after = {"sample.py": {"sha256": "bbb"}}
        with patch.object(runner, 'source_hashes', side_effect=[before, after]):
            with patch.object(runner.subprocess, 'run', side_effect=self.fake_run()):
                self.assertEqual(runner.main(['--suite', 'lifecycle', '--output-dir', str(self.output)]), 1)
        result = json.loads((self.output / 'receipt.json').read_text())
        self.assertFalse(result['sources_unchanged'])

    def test_existing_output_directory_is_not_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / 'receipt.json'
        sentinel.write_text('previous evidence')
        with patch.object(runner.subprocess, 'run') as process:
            self.assertEqual(runner.main(['--output-dir', str(self.output)]), 2)
            process.assert_not_called()
        self.assertEqual(sentinel.read_text(), 'previous evidence')


if __name__ == '__main__':
    unittest.main()
