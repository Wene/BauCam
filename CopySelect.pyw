#!/usr/bin/env python3

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from datetime import datetime
import sqlite3

class Form(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings()
        title = 'CopySelect [' + app.applicationVersion() + ']'
        self.setWindowTitle(title)

        main_layout = QGridLayout(self)

        lbl_time = QLabel('Zeit (HH:MM)')
        lbl_tolerance = QLabel('Toleranz (± Minuten)')
        lbl_skip = QLabel('Wochentage auslassen (Sa, So)')
        self.edt_time = QLineEdit()
        self.edt_tolerance = QLineEdit()
        self.edt_skip = QLineEdit()
        main_layout.addWidget(lbl_time, 0, 0)
        main_layout.addWidget(self.edt_time, 0, 1)
        main_layout.addWidget(lbl_tolerance, 1, 0)
        main_layout.addWidget(self.edt_tolerance, 1, 1)
        main_layout.addWidget(lbl_skip, 2, 0)
        main_layout.addWidget(self.edt_skip, 2, 1)

        self.btn_solve = QPushButton('Aus&werten')
        self.btn_solve.clicked.connect(self.solve)
        main_layout.addWidget(self.btn_solve, 3, 1)

        self.btn_copy = QPushButton('K&opieren...')
        self.btn_copy.clicked.connect(self.copy)
        main_layout.addWidget(self.btn_copy, 4, 1)

        self.btn_quit = QPushButton('B&eenden')
        self.btn_quit.clicked.connect(self.close)
        main_layout.addWidget(self.btn_quit, 5, 1)

        self.resize(self.settings.value('windowSize', QSize(50, 50)))
        self.move(self.settings.value('windowPosition', QPoint(50, 50)))
        self.edt_time.setText(self.settings.value('time', '12:00'))
        self.edt_tolerance.setText(self.settings.value('tolerance', '60'))
        self.edt_skip.setText(self.settings.value('skip', 'Sa, So'))

    def closeEvent(self, a0: QCloseEvent) -> None:
        self.settings.setValue('windowSize', self.size())
        self.settings.setValue('windowPosition', self.pos())
        self.settings.setValue('time', self.edt_time.text())
        self.settings.setValue('tolerance', self.edt_tolerance.text())
        self.settings.setValue('skip', self.edt_skip.text())

    def solve(self):
        pass

    def copy(self):
        path = QFileDialog.getExistingDirectory(self, 'Zielverzeichnis')
        if path:
            print('Path:', path)
        else:
            print('no path')


if __name__ == '__main__':
    import sys
    import configparser

    conf = configparser.ConfigParser()
    conf.read('BauCam.conf')
    general_conf = conf['general']

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
