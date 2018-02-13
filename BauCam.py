#!/usr/bin/env python3

import os
import subprocess
from time import sleep
from datetime import datetime, timedelta


def take_photos():
    os.chdir('pictures/capture')

    now = datetime.now()
    last_time = now - timedelta(seconds=28)
    for i in range(10):
        # calculate cycle time
        while now < last_time + timedelta(seconds=30):
            now = datetime.now()
            print(now.isoformat(), last_time.isoformat())
            sleep(1)
        last_time = now

        # clean up the directory
        files = os.listdir()
        for file_name in files:
            os.remove(file_name)

        try:
            out_bytes = subprocess.run(['gphoto2', '--capture-image-and-download'], timeout=15,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout
            output = str(out_bytes, 'utf-8')
            print('Ausgabe:')
            print('---')
            print(str(output))
            files = os.listdir()
            for file_name in files:
                base, ext = os.path.splitext(file_name)
                pic_name = now.strftime('img_%Y-%m-%d_%H-%M-%S')
                os.rename(file_name, os.path.join('..', pic_name + ext))
        except subprocess.TimeoutExpired as e:
            print('Timeout beim Versuch zu fotografieren...')
        except Exception as e:
            print('Unbekannter Ausnahmefehler:')
            print(type(e))
            print(e)


if __name__ == '__main__':
    if datetime.now() > datetime(2018, 2, 1, 0, 0):
        take_photos()
    else:
        print('Systemdatum falsch')