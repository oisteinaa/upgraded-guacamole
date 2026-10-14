#!/usr/bin/env python3
"""PyQt6 front end: job settings map directly to CLI arguments; no conversion logic."""
import json
import shlex
import sys
from pathlib import Path
from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox, QSpinBox, QPushButton,
    QFileDialog, QMessageBox, QProgressBar, QLabel, QGroupBox,
)

ROOT = Path(__file__).resolve().parent


def build_arguments(job, dry_run=False):
    args = []
    for path in job['inputs'].splitlines():
        if path.strip():
            args += ['--input', path.strip()]
    for key, flag in [('channels', '--channels'), ('receivers', '--receivers-csv'),
                      ('lid', '--lid'), ('mode', '--mode'), ('format', '--format'),
                      ('output', '--output')]:
        args += [flag, str(job[key])]
    for key in ('start', 'end'):
        if job[key].strip():
            args += ['--' + key, job[key].strip()]
    if job['mode'] == 'continuous':
        args += ['--trace-length', str(job['trace_length'])]
    else:
        for path in job['p111'].splitlines():
            if path.strip():
                args += ['--p111', path.strip()]
        args += ['--p111-crs', job['crs'], '--duration', str(job['duration']),
                 '--offset', str(job['offset'])]
    if dry_run:
        args += ['--dry-run']
    return args


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('DAS Transcriber — H5 to SEG-Y / SEG-D')
        self.resize(950, 850)
        self.process = None
        self.validated = None
        self.buffer = ''
        self.got_preflight = False
        self.controls = {}
        body = QWidget()
        self.setCentralWidget(body)
        layout = QVBoxLayout(body)
        self.editor = QGroupBox('Conversion job')
        form = QFormLayout(self.editor)
        layout.addWidget(self.editor)

        def line(key, label, default='', browse=None):
            widget = QLineEdit(default)
            self.controls[key] = widget
            row = QHBoxLayout()
            row.addWidget(widget)
            if browse:
                button = QPushButton('Browse…')
                button.clicked.connect(lambda: self.browse_line(key, browse))
                row.addWidget(button)
            form.addRow(label, row)
            widget.textChanged.connect(self.changed)
            return widget

        executable = ROOT / 'target/release/rust_transcriber'
        if not executable.exists():
            executable = ROOT / 'target/debug/rust_transcriber'
        line('executable', 'CLI executable', str(executable), 'file')
        for key, label, filters in [('inputs', 'H5 inputs (one path or glob per line)', 'HDF5 (*.h5 *.hdf5)'),
                                    ('p111', 'P1/11 navigation (shot mode)', 'Navigation (*.p111 *.P111);;All files (*)')]:
            widget = QPlainTextEdit()
            widget.setMaximumHeight(70)
            self.controls[key] = widget
            row = QHBoxLayout()
            row.addWidget(widget)
            buttons = QVBoxLayout()
            files = QPushButton('Add files…')
            files.clicked.connect(lambda _, k=key, f=filters: self.add_files(k, f))
            buttons.addWidget(files)
            if key == 'inputs':
                directory = QPushButton('Add directory…')
                directory.clicked.connect(self.add_directory)
                buttons.addWidget(directory)
            row.addLayout(buttons)
            form.addRow(label, row)
            widget.textChanged.connect(self.changed)
        line('receivers', 'Receiver CSV (exact native channel matches)', browse='csv')
        line('channels', 'Native channels', 'all')
        lid = QSpinBox()
        lid.setRange(1, 8388607)
        lid.setValue(1)
        self.controls['lid'] = lid
        form.addRow('DAS line ID', lid)
        lid.valueChanged.connect(self.changed)
        for key, label, values in [('mode', 'Mode', ['continuous', 'shot']),
                                   ('format', 'Output format', ['segy', 'segd', 'both']),
                                   ('crs', 'P1/11 source XY coordinates', ['utm33n', 'wgs84'])]:
            combo = QComboBox()
            combo.addItems(values)
            self.controls[key] = combo
            form.addRow(label, combo)
            combo.currentTextChanged.connect(self.changed)
        for key, label, value, low in [('trace_length', 'Continuous trace length (seconds)', 60., .000001),
                                       ('duration', 'Shot duration (seconds)', 10., .000001),
                                       ('offset', 'Shot start offset (seconds)', 0., -2147.)]:
            spin = QDoubleSpinBox()
            spin.setDecimals(6)
            spin.setRange(low, 2147.)
            spin.setValue(value)
            self.controls[key] = spin
            form.addRow(label, spin)
            spin.valueChanged.connect(self.changed)
        line('start', 'Start (optional RFC3339, e.g. 2026-09-24T00:00:00Z)')
        line('end', 'End (exclusive, optional RFC3339)')
        line('output', 'Output directory', browse='directory')
        self.command = QLineEdit()
        self.command.setReadOnly(True)
        layout.addWidget(QLabel('Equivalent command'))
        layout.addWidget(self.command)
        row = QHBoxLayout()
        self.load = QPushButton('Load job…')
        self.save = QPushButton('Save job…')
        self.validate = QPushButton('Check inputs')
        self.start = QPushButton('Start conversion')
        self.cancel = QPushButton('Cancel')
        self.cancel.setEnabled(False)
        for b in (self.load, self.save, self.validate, self.start, self.cancel):
            row.addWidget(b)
        layout.addLayout(row)
        self.load.clicked.connect(self.load_job)
        self.save.clicked.connect(self.save_job)
        self.validate.clicked.connect(lambda: self.launch(True))
        self.start.clicked.connect(lambda: self.launch(False))
        self.cancel.clicked.connect(self.cancel_job)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        layout.addWidget(self.log)
        self.changed()

    def job(self):
        result = {}
        for key, widget in self.controls.items():
            if isinstance(widget, QLineEdit):
                result[key] = widget.text()
            elif isinstance(widget, QPlainTextEdit):
                result[key] = widget.toPlainText()
            elif isinstance(widget, QComboBox):
                result[key] = widget.currentText()
            else:
                result[key] = widget.value()
        return result

    def changed(self, *_):
        self.validated = None
        if not hasattr(self, 'command'):
            return
        job = self.job()
        self.command.setText(shlex.join([job['executable'], *build_arguments(job)]))
        self.command.setCursorPosition(0)
        self.start.setEnabled(False)
        shot = job['mode'] == 'shot'
        for key in ('p111', 'duration', 'offset', 'crs'):
            self.controls[key].setEnabled(shot)
        self.controls['trace_length'].setEnabled(not shot)

    def browse_line(self, key, kind):
        if kind == 'directory':
            path = QFileDialog.getExistingDirectory(self, 'Select directory')
        else:
            path, _ = QFileDialog.getOpenFileName(self, 'Select file', '', 'CSV (*.csv);;All files (*)' if kind == 'csv' else 'All files (*)')
        if path:
            self.controls[key].setText(path)

    def add_files(self, key, filters):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Select files', '', filters)
        if paths:
            self.controls[key].appendPlainText('\n'.join(paths))

    def add_directory(self):
        path = QFileDialog.getExistingDirectory(self, 'Select H5 archive directory')
        if path:
            self.controls['inputs'].appendPlainText(path)

    def save_job(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save job', '', 'JSON (*.json)')
        if path:
            try:
                Path(path).write_text(json.dumps(self.job(), indent=2))
            except OSError as error:
                QMessageBox.warning(self, 'Save failed', str(error))

    def load_job(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Load job', '', 'JSON (*.json)')
        if not path:
            return
        try:
            job = json.loads(Path(path).read_text())
            for key, value in job.items():
                if key not in self.controls:
                    continue
                widget = self.controls[key]
                if isinstance(widget, QLineEdit):
                    widget.setText(str(value))
                elif isinstance(widget, QPlainTextEdit):
                    widget.setPlainText(str(value))
                elif isinstance(widget, QComboBox):
                    if str(value) not in [widget.itemText(i) for i in range(widget.count())]:
                        raise ValueError(f'Invalid {key}')
                    widget.setCurrentText(str(value))
                else:
                    widget.setValue(value)
            self.changed()
        except (OSError, ValueError, TypeError, AttributeError) as error:
            QMessageBox.warning(self, 'Invalid job', str(error))

    def launch(self, dry_run):
        job = self.job()
        if self.process is not None or (not dry_run and job != self.validated):
            return
        self.dry_run = dry_run
        self.running_job = job
        self.got_preflight = False
        self.buffer = ''
        self.log.clear()
        self.progress.setRange(0, 0)
        self.editor.setEnabled(False)
        for button in (self.load, self.save, self.start, self.validate):
            button.setEnabled(False)
        self.cancel.setEnabled(True)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.process.start(job['executable'], build_arguments(job, dry_run))

    def read_output(self):
        if self.process is None:
            return
        self.buffer += bytes(self.process.readAllStandardOutput()).decode(errors='replace')
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            try:
                event = json.loads(line)
            except ValueError:
                self.log.appendPlainText(line)
                continue
            if event.get('event') == 'progress':
                self.progress.setRange(0, event['total'])
                self.progress.setValue(event['completed'])
            elif event.get('event') == 'preflight':
                self.got_preflight = True
                channels = event['selected_channels']
                self.log.appendPlainText(f'Selected {len(channels)} native channels: {channels[:30]}' + (' …' if len(channels) > 30 else ''))
                for output in event['files']:
                    self.log.appendPlainText(f"{output['path']}: {output['records']} records, {output['bytes'] / 1e9:.3f} GB")
                self.log.appendPlainText(f"Skipped shots: {len(event['skipped_shots'])}")
            else:
                self.log.appendPlainText(event.get('message', line))

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.log.appendPlainText(self.process.errorString())
            self.finished(1)

    def finished(self, code, *_):
        self.read_output()
        if self.buffer:
            self.log.appendPlainText(self.buffer)
        self.log.appendPlainText(f'Process exited with code {code}.')
        if self.process:
            self.process.deleteLater()
        self.process = None
        self.editor.setEnabled(True)
        for button in (self.load, self.save, self.validate):
            button.setEnabled(True)
        self.cancel.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if code == 0 else 0)
        self.validated = self.running_job if code == 0 and self.dry_run and self.got_preflight else None
        self.start.setEnabled(self.validated is not None)

    def cancel_job(self):
        if self.process:
            self.process.terminate()
            self.cancel.setEnabled(False)
            self.log.appendPlainText('Cancellation requested; waiting for temporary-file cleanup.')

    def closeEvent(self, event):
        if self.process is not None:
            self.cancel_job()
            event.ignore()
        else:
            event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())
