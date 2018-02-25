#!/usr/bin/env python3

import os
import subprocess
import exifread
import configparser
import sqlite3
from time import sleep
from datetime import datetime, timedelta
import gpiozero
import sys


def take_photo(capture_path, local_path, pic_name):
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
        ret = ['']
        files = os.listdir()
        for file_name in files:
            base, ext = os.path.splitext(file_name)
            new_name = pic_name + ext
            os.rename(file_name, os.path.join(local_path, new_name))
            if '.jpg' == ext.lower() or '.jpeg' == ext.lower():
                ret[0] = new_name
            else:
                ret.append(new_name)
        return ret
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

    # connect relais module and restart camera
    camera = gpiozero.DigitalOutputDevice(pin=3, active_high=False)
    camera.off()
    sleep(5)
    camera.on()

    # check if the clock is possibly set correctly (this script should run on a Raspberry Pi without RTC)
    if datetime.now() > datetime(2018, 2, 1, 0, 0):
        now = datetime.now()
        last_time = now - timedelta(seconds=interval - 2)
        no_photo_taken = 0
        for i in range(10):
            # calculate cycle time
            while now < last_time + timedelta(seconds=interval):
                now = datetime.now()
                diff = now - last_time
                print(diff.total_seconds())
                sleep(1)
            last_time = now
            pic_name = now.strftime('img_%Y-%m-%d_%H-%M-%S')
            files = take_photo(capture_path, local_path, pic_name)
            if files[0] != '':
                no_photo_taken = 0
                exif_path = os.path.join(local_path, files[0])
                with open(exif_path, 'rb') as f:
                    exif_tags = exifread.process_file(f)
                print('Dateiname', exif_path)
                print('Verschlusszeit', exif_tags['EXIF ExposureTime'])
                print('ISO', exif_tags['EXIF ISOSpeedRatings'])
                print('Blende', exif_tags['EXIF FNumber'])
                print('Aufnahmedatum', exif_tags['EXIF DateTimeOriginal'])
            else:
                no_photo_taken += 1
            # TODO: take actual rebooting measures
            if no_photo_taken > 3:
                print('rebooting everything')
                sys.exit('reboot required')
            if no_photo_taken > 2:
                print('rebooting camera')
                camera.off()
                sleep(10)
                camera.on()

    else:
        print('Systemdatum falsch')