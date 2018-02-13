#!/usr/bin/env python3

import os
import subprocess
from time import sleep
from datetime import datetime


def take_photos():
    os.chdir('pictures/capture')

    for i in range(10):
        pic_name = datetime.now().strftime('img_%Y-%m-%d_%H-%M-%S')

        # clean up the directory
        files = os.listdir()
        for file_name in files:
            os.remove(file_name)

        try:
            out_bytes = subprocess.run(['gphoto2', '--capture-image-and-download'], timeout=15, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout
            output = str(out_bytes, 'utf-8')
            print('Ausgabe:')
            print('---')
            print(str(output))
            files = os.listdir()
            for file_name in files:
                base, ext = os.path.splitext(file_name)
                os.rename(file_name, os.path.join('..', pic_name + ext))
        except Exception as e:
            print('Unbekannter Ausnahmefehler:')
            print(type(e))
            print(e)
        sleep(10)


if __name__ == '__main__':
    if datetime.now() > datetime(2018, 2, 1, 0, 0):
        take_photos()
    else:
        print('Systemdatum falsch')