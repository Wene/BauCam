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
        # print('Ausgabe:')
        # print('---')
        # print(str(output))
        final_names = ['']
        files = os.listdir()
        for file_name in files:
            base, ext = os.path.splitext(file_name)
            new_name = pic_name + ext
            os.rename(file_name, os.path.join(local_path, new_name))
            if '.jpg' == ext.lower() or '.jpeg' == ext.lower():
                final_names[0] = new_name
            else:
                final_names.append(new_name)
        return final_names, output
    except subprocess.TimeoutExpired as e:
        print('Timeout beim Versuch zu fotografieren...')
    except Exception as e:
        print('Unbekannter Ausnahmefehler:')
        print(type(e))
        print(e)


def extract_exif(file_path, timestamp):
    # read EXIF tags from the image
    with open(file_path, 'rb') as f:
        all_tags = exifread.process_file(f)
    exif = {'exposure_time': all_tags['EXIF ExposureTime'],
            'iso': all_tags['EXIF ISOSpeedRatings'],
            'aperture': all_tags['EXIF FNumber'],
            'timestamp': all_tags['EXIF DateTimeOriginal']}

    # Debugging output
    # print('Dateiname', file_path)
    # print('Timestamp', timestamp.strftime('%Y-%m-%d %H:%M:%S'))
    # print('Verschlusszeit', all_tags['EXIF ExposureTime'])
    # print('ISO', all_tags['EXIF ISOSpeedRatings']
    # print('Blende', all_tags['EXIF FNumber'])
    # print('Aufnahmedatum', all_tags['EXIF DateTimeOriginal'])

    return exif


def store_in_database(timestamp, filename, exif_tags, output):
    # store data in database
    os.chdir(local_path)
    conn = sqlite3.connect('images.db')
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS '
                'images (timestamp, filename, exposure_time, iso, aperture, exif_timestamp, output)')
    cur.execute('INSERT INTO images (timestamp, filename, exposure_time, iso, aperture, exif_timestamp, output) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)', (timestamp, filename, exif_tags['exposure_time'],
                exif_tags['iso'], exif_tags['aperture'], exif_tags['timestamp'], output))
    conn.commit()
    conn.close()


def restart_camera():
    camera.off()
    sleep(5)
    camera.on()
    sleep(5)


def photo_loop():
    now = datetime.now()
    last_time = now - timedelta(seconds=interval - 2)
    no_photo_taken = 0

    # TODO: insert infinite loop here
    for i in range(20):

        # calculate cycle time
        while now < last_time + timedelta(seconds=interval):
            now = datetime.now()
            diff = now - last_time
            print(diff.total_seconds())
            sleep(1)
        last_time = now

        # take a photo
        pic_name = now.strftime('img_%Y-%m-%d_%H-%M-%S')
        files, output = take_photo(capture_path, local_path, pic_name)
        if files[0] != '':
            no_photo_taken = 0
            exif_path = os.path.join(local_path, files[0])
            exif_tags = extract_exif(exif_path, now)
            store_in_database(now, files[0], exif_tags, output)
        else:
            no_photo_taken += 1
            store_in_database(now, '', {'exposure_time': '', 'iso': '', 'aperture': '', 'timestamp': ''}, output)
        if no_photo_taken > 3:
            print('rebooting everything')
            subprocess.run(['sudo', 'reboot'])  # works only on systems with sudo without password (RasPi)
            sys.exit('reboot triggered')
        if no_photo_taken > 2:
            print('rebooting camera')
            restart_camera()
        if no_photo_taken > 0:
            print('system will be rebooted after', 4 - no_photo_taken, 'failures.')


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

    # connect relays module and restart camera
    camera = gpiozero.DigitalOutputDevice(pin=2, active_high=True)
    restart_camera()

    # check if the clock is possibly set correctly (this script should run on a Raspberry Pi without RTC)
    if datetime.now() > datetime(2018, 2, 1, 0, 0):
        photo_loop()
    else:
        print('Systemdatum falsch')

