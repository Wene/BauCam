#!/usr/bin/env python3

import os
import subprocess
import exifread
import configparser
import sqlite3
from time import sleep
from datetime import datetime, timedelta


def take_photo(capture_path, local_path):
    os.chdir(capture_path)

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
            os.rename(file_name, os.path.join(local_path, pic_name + ext))
        return files
    except subprocess.TimeoutExpired as e:
        print('Timeout beim Versuch zu fotografieren...')
    except Exception as e:
        print('Unbekannter Ausnahmefehler:')
        print(type(e))
        print(e)


if __name__ == '__main__':
    # read configuration
    conf = configparser.ConfigParser()
    if os.path.isfile('BauCam.conf'):
        conf.read('BauCam.conf')
    # create new default config file if it doesn't exist
    if 'general' not in conf.sections():
        conf['general'] = {'capture path': '/tmp/BauCam',
                           'local path': '~/BauCam/images',
                           'remote path': '~/BauCam/remote',
                           'interval seconds': '30'}
        with open('BauCam.conf', 'w') as f:
            conf.write(f)
    general_conf = conf['general']
    # read all paths and create them if they don't exist
    capture_path = os.path.expanduser(general_conf.get('capture path'))
    local_path = os.path.expanduser(general_conf.get('local path'))
    remote_path = os.path.expanduser(general_conf.get('remote path'))
    if not os.path.isdir(capture_path):
        os.makedirs(capture_path)
    if not os.path.isdir(local_path):
        os.makedirs(local_path)
    if not os.path.isdir(remote_path):
        os.makedirs(remote_path)
    interval = general_conf.getint('interval seconds')

    # check if the clock is possibly set correctly (this script should run on a Raspberry Pi without RTC)
    if datetime.now() > datetime(2018, 2, 1, 0, 0):
        now = datetime.now()
        last_time = now - timedelta(seconds=interval - 2)
        for i in range(10):
            # calculate cycle time
            while now < last_time + timedelta(seconds=interval):
                now = datetime.now()
                print(now.isoformat(), last_time.isoformat())
                sleep(1)
            last_time = now
            files = take_photo(capture_path, local_path)
            for name in files:
                print(name)
    else:
        print('Systemdatum falsch')