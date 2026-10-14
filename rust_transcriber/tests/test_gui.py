"""Offscreen GUI/CLI lifecycle checks."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui import QApplication, Window, build_arguments
from test_conversion import h5, BIN

APP = QApplication.instance() or QApplication([])


class Gui(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.window = Window()
        source = self.root / 'source.h5'
        h5(source)
        receiver = self.root / 'receivers.csv'
        receiver.write_text('lid,channel,latitude,longitude\n1,0,68,14\n1,4,68,14\n1,50000,68,14\n')
        c = self.window.controls
        c['executable'].setText(str(BIN))
        c['inputs'].setPlainText(str(source))
        c['receivers'].setText(str(receiver))
        c['output'].setText(str(self.root / 'out'))

    def tearDown(self):
        self.window.close()
        self.temp.cleanup()

    def wait(self):
        deadline = time.monotonic() + 10
        while self.window.process is not None and time.monotonic() < deadline:
            APP.processEvents()
            time.sleep(.01)
        self.assertIsNone(self.window.process)

    def test_preflight_then_conversion(self):
        self.assertEqual(self.window.job()['trace_length'], 60.)
        self.assertFalse(self.window.start.isEnabled())
        self.window.launch(True)
        self.wait()
        self.assertTrue(self.window.start.isEnabled(), self.window.log.toPlainText())
        self.window.launch(False)
        self.wait()
        self.assertTrue(list((self.root / 'out').glob('*.sgy')))
        self.assertFalse(self.window.start.isEnabled())

    def test_edit_invalidates_preflight(self):
        self.window.launch(True)
        self.wait()
        self.window.controls['trace_length'].setValue(15)
        self.assertFalse(self.window.start.isEnabled())
        self.assertIn('15.0', build_arguments(self.window.job()))

    def test_invalid_executable_recovers(self):
        self.window.controls['executable'].setText('/does/not/exist')
        self.window.launch(True)
        self.wait()
        self.assertTrue(self.window.validate.isEnabled())
        self.assertFalse(self.window.start.isEnabled())

    def test_validation_error_does_not_enable_start(self):
        self.window.controls['channels'].setText('8')
        self.window.launch(True)
        self.wait()
        self.assertFalse(self.window.start.isEnabled())
        self.assertIn('code 1', self.window.log.toPlainText())

    def test_shot_arguments(self):
        self.window.controls['mode'].setCurrentText('shot')
        self.window.controls['p111'].setPlainText('/tmp/shot one.p111\n/tmp/shot two.p111')
        args = build_arguments(self.window.job())
        self.assertEqual(args.count('--p111'), 2)
        self.assertNotIn('--trace-length', args)
        self.assertIn('/tmp/shot one.p111', args)


if __name__ == '__main__':
    unittest.main()
