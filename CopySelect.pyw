#!/usr/bin/env python3
import os
import shutil
import sqlite3

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *


class Form(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings()
        title = 'CopySelect [' + app.applicationVersion() + ']'
        self.setWindowTitle(title)

        self.data = {}
        self.result_ids = []
        self.copy_state = {}

        self.copy_timer = QTimer(self)
        self.copy_timer.setInterval(10)
        self.copy_timer.setSingleShot(False)
        self.copy_timer.stop()
        self.copy_timer.timeout.connect(self.copy_one)

        main_layout = QGridLayout(self)

        self.lbl_db = QLabel('Keine Datenbank geladen')
        main_layout.addWidget(self.lbl_db, 0, 0)
        self.btn_load_db = QPushButton('Datenbank &Laden...')
        self.btn_load_db.clicked.connect(self.load_db)
        main_layout.addWidget(self.btn_load_db, 0, 1)

        lbl_time = QLabel('Zeit (HH:MM)')
        lbl_tolerance = QLabel('Toleranz (± Minuten)')
        lbl_skip = QLabel('Wochentage auslassen (Sa, So)')
        self.edt_time = QLineEdit()
        self.edt_tolerance = QLineEdit()
        self.edt_tolerance.setValidator(QIntValidator(0, 120))
        self.edt_skip = QLineEdit()
        main_layout.addWidget(lbl_time, 1, 0)
        main_layout.addWidget(self.edt_time, 1, 1)
        main_layout.addWidget(lbl_tolerance, 2, 0)
        main_layout.addWidget(self.edt_tolerance, 2, 1)
        main_layout.addWidget(lbl_skip, 3, 0)
        main_layout.addWidget(self.edt_skip, 3, 1)

        self.btn_solve = QPushButton('Aus&werten')
        self.btn_solve.clicked.connect(self.solve)
        main_layout.addWidget(self.btn_solve, 4, 1)

        self.edt_result = QPlainTextEdit()
        self.edt_result.setReadOnly(True)
        self.edt_result.setUndoRedoEnabled(False)
        main_layout.addWidget(self.edt_result, 5, 0, 1, 2)

        self.lbl_source = QLabel('Kein Quellverzeichnis ausgewählt')
        main_layout.addWidget(self.lbl_source, 6, 0)
        self.btn_source = QPushButton('&Quellverzeichnis...')
        self.btn_source.clicked.connect(self.source_select)
        main_layout.addWidget(self.btn_source, 6, 1)

        self.btn_copy = QPushButton('K&opieren...')
        self.btn_copy.clicked.connect(self.copy)
        main_layout.addWidget(self.btn_copy, 7, 1)
        self.pro_copy = QProgressBar()
        self.pro_copy.setVisible(False)
        main_layout.addWidget(self.pro_copy, 7, 0)

        self.btn_quit = QPushButton('B&eenden')
        self.btn_quit.clicked.connect(self.close)
        main_layout.addWidget(self.btn_quit, 8, 1)

        self.resize(self.settings.value('windowSize', QSize(50, 50)))
        self.move(self.settings.value('windowPosition', QPoint(50, 50)))
        self.edt_time.setText(self.settings.value('time', '12:00'))
        self.edt_tolerance.setText(self.settings.value('tolerance', '60'))
        self.edt_skip.setText(self.settings.value('skip', 'Sa, So'))
        self.source_path = self.settings.value('source_path', '')
        if self.source_path:
            self.lbl_source.setText(self.source_path)

    def closeEvent(self, a0: QCloseEvent) -> None:
        self.settings.setValue('windowSize', self.size())
        self.settings.setValue('windowPosition', self.pos())
        self.settings.setValue('time', self.edt_time.text())
        self.settings.setValue('tolerance', self.edt_tolerance.text())
        self.settings.setValue('skip', self.edt_skip.text())

    def load_db(self):
        last_path = self.settings.value('db_path', '')
        path, _ = QFileDialog.getOpenFileName(self, 'Datenbank laden', last_path, 'Datenbank dateien (*.db)')
        if path:
            self.settings.setValue('db_path', path)
            file_path, file_name = os.path.split(path)
            self.lbl_db.setText(file_name)
            db_connection = sqlite3.connect(path)
            db_cursor = db_connection.cursor()
            db_cursor.execute('SELECT i.id, i.raspi_time, f.name FROM images AS i, files AS f '
                              'WHERE i.id = f.images_id AND f.name like "%.jpg" ORDER BY i.id')
            rows = db_cursor.fetchall()
            db_cursor.close()
            db_connection.close()
            self.data.clear()
            for image in rows:
                id = int(image[0])
                time_str = image[1].split('.')[0]
                time = QDateTime.fromString(time_str, 'yyyy-MM-dd hh:mm:ss')
                self.data[id] = (time, image[2])

    def solve(self):
        self.edt_result.clear()
        self.result_ids.clear()
        search_time = QTime.fromString(self.edt_time.text(), 'hh:mm')
        if not search_time.isValid():
            QMessageBox.critical(self, 'Fehler', 'Ungültige Zeit eingegeben')
            return

        max_tolerance_seconds = int(self.edt_tolerance.text()) * 60
        current_date = QDate()
        result_today = {}
        index: int
        date_time: QDateTime
        for index, data_set in self.data.items():
            date_time = data_set[0]
            week_day = date_time.toString('ddd')[0:2]
            if week_day in self.edt_skip.text():
                continue
            time = date_time.time()
            date = date_time.date()

            # store best hit if the date has changed
            if date != current_date:
                if len(result_today) > 0:
                    best_result = sorted(result_today)[0]
                    result = result_today[best_result]
                    self.result_ids.append(result[0])
                    text = str(result[0]) + ': ' + result[1].toString()
                    self.edt_result.appendPlainText(text)
                    result_today.clear()
                current_date = date

            # filter date_time's in tolerance range
            deviation_seconds = 0
            while deviation_seconds <= max_tolerance_seconds:
                min_time = QTime.addSecs(search_time, -deviation_seconds)
                max_time = QTime.addSecs(search_time, deviation_seconds)
                if min_time <= time <= max_time:
                    result_today[deviation_seconds] = (index, date_time)
                    break
                else:
                    deviation_seconds += 60
        self.edt_result.appendPlainText(f'Total: {len(self.result_ids)}')

    def source_select(self):
        path = QFileDialog.getExistingDirectory(self, 'Quellverzeichnis', self.source_path)
        if path:
            self.settings.setValue('source_path', path)
            self.lbl_source.setText(path)
            self.source_path = path

    def copy(self):
        last_path = self.settings.value('target_path', '')
        target_path = QFileDialog.getExistingDirectory(self, 'Zielverzeichnis', last_path)
        if target_path:
            self.settings.setValue('target_path', target_path)
            self.pro_copy.setMaximum(len(self.result_ids))
            self.pro_copy.setValue(0)
            self.pro_copy.setVisible(True)
            self.copy_state['target_path'] = target_path
            self.copy_state['result_idx'] = 0
            self.copy_state['good_count'] = 0
            self.copy_state['bad_count'] = 0
            self.copy_timer.start()
            self.enable_ui(False)

    def copy_one(self):
        target_path = self.copy_state['target_path']
        result_idx = self.copy_state['result_idx']
        if result_idx < len(self.result_ids):
            index = self.result_ids[result_idx]
            file_name = self.data[index][1]
            file_path = os.path.join(self.source_path, file_name)
            if os.path.exists(file_path):
                target_path = os.path.join(target_path, file_name)
                if not os.path.exists(target_path):
                    shutil.copyfile(file_path, target_path)
                self.copy_state['good_count'] += 1
            else:
                self.edt_result.appendPlainText(f'Datei {file_path} nicht gefunden')
                self.copy_state['bad_count'] += 1
            self.copy_state['result_idx'] += 1
            self.pro_copy.setValue(result_idx)
        else:
            self.edt_result.appendPlainText(f'{self.copy_state["good_count"]} Dateien kopiert, '
                                            f'{self.copy_state["bad_count"]} Dateien nicht gefunden')
            self.pro_copy.setVisible(False)
            self.copy_timer.stop()
            self.enable_ui(True)

    def enable_ui(self, enable_state: bool):
        self.btn_copy.setEnabled(enable_state)
        self.btn_solve.setEnabled(enable_state)
        self.btn_source.setEnabled(enable_state)
        self.btn_load_db.setEnabled(enable_state)
        self.edt_skip.setEnabled(enable_state)
        self.edt_time.setEnabled(enable_state)
        self.edt_tolerance.setEnabled(enable_state)


if __name__ == '__main__':
    import sys

    app = QApplication(sys.argv)

    app.setOrganizationName('Wene')
    app.setApplicationName('BauCam_CopySelect')
    app.setApplicationVersion('0.1.0')

    translator = QTranslator()
    lib_path = QLibraryInfo.location(QLibraryInfo.TranslationsPath)
    translator.load("qt_de.qm", lib_path)
    translator.load("qtbase_de.qm", lib_path)
    app.installTranslator(translator)

    window = Form()
    window.show()

    sys.exit(app.exec_())
