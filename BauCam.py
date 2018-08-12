#!/usr/bin/env python3

import os
import signal
import subprocess
import exifread
import configparser
import sqlite3
from time import sleep
from datetime import datetime, timedelta
import gpiozero
import sys
import Adafruit_DHT


class KillWatcher:
    kill_now = False

    def __init__(self):
        signal.signal(signal.SIGTERM, self.handler)
        signal.signal(signal.SIGINT, self.handler)

    def handler(self, signum, frame):
        self.kill_now = True


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


def extract_exif(file_path):
    # read EXIF tags from the image
    exif_date_format = '%Y:%m:%d %H:%M:%S'
    with open(file_path, 'rb') as f:
        all_tags = exifread.process_file(f)
    timestamp = datetime.strptime(str(all_tags['EXIF DateTimeOriginal']), exif_date_format)
    return all_tags, timestamp


def create_database():
    os.chdir(local_path)
    conn = sqlite3.connect('images.db')
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS "images" ("raspi_time" TEXT, "camera_time" TEXT, "gphoto_output" TEXT);')
    cur.execute('CREATE TABLE IF NOT EXISTS "files" ("images_rowid" INTEGER NOT NULL, "name" TEXT NOT NULL, '
                '"local_copy" INTEGER NOT NULL DEFAULT (1), "remote_copy" INTEGER NOT NULL DEFAULT (0));')
    cur.execute('CREATE TABLE IF NOT EXISTS "tags" ("images_rowid" INTEGER NOT NULL, '
                '"name" TEXT NOT NULL, "value" TEXT);')
    conn.commit()
    conn.close()


def store_in_database(timestamp, output, cam_time=None, file_names=[], exif_tags={}):
    # store data in database
    os.chdir(local_path)
    conn = sqlite3.connect('images.db')
    cur = conn.cursor()

    cur.execute('INSERT INTO images (raspi_time, camera_time, gphoto_output) '
                'VALUES (?, ?, ?)', (timestamp, cam_time, output))
    cur.execute('SELECT last_insert_rowid()')
    row_id = cur.fetchone()[0]
    for name in file_names:
        cur.execute('INSERT INTO files (images_rowid, name, local_copy, remote_copy) VALUES (?, ?, ?, ?)',
                    (row_id, name, 1, 0))
    for key, value in exif_tags.items():
        if key.startswith('EXIF') and len(str(value)) < 150:
            cur.execute('INSERT INTO tags (images_rowid, name, value) VALUES (?, ?, ?)', (row_id, key, str(value)))
    conn.commit()
    conn.close()


def restart_camera():
    camera.off()
    sleep(5)
    camera.on()
    sleep(5)


def main_loop():
    last_photo = datetime.now()- timedelta(seconds=photo_interval - 2)
    last_climate = datetime.now() - timedelta(seconds=climate_interval - 2)
    no_photo_taken = 0

    while not watcher.kill_now:
        now = datetime.now()

        if now >= last_photo + timedelta(seconds=photo_interval):
            last_photo = now
            pic_name = now.strftime('img_%Y-%m-%d_%H-%M-%S')
            files, output = take_photo(capture_path, local_path, pic_name)
            if files[0] != '':
                no_photo_taken = 0
                jpeg_path = os.path.join(local_path, files[0])
                exif_tags, cam_time = extract_exif(jpeg_path)
                store_in_database(now, output, cam_time=cam_time, file_names=files, exif_tags=exif_tags)
            else:
                no_photo_taken += 1
                store_in_database(now, output)
            if no_photo_taken > 3:
                print('rebooting everything')
                subprocess.run(['sudo', 'reboot'])  # works only on systems with sudo without password (RasPi)
                sys.exit('reboot triggered')
            if no_photo_taken > 2:
                print('rebooting camera')
                restart_camera()
            if no_photo_taken > 0:
                print('system will be rebooted after', 4 - no_photo_taken, 'failures.')

        if now >= last_climate + timedelta(seconds=climate_interval):
            last_climate = now
            humidity, temperature = Adafruit_DHT.read(sensor, sensor_pin)
            print('Humidity', humidity)
            print('Temperature', temperature)

        sleep(1)


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
                           'photo interval': '600',
                           'climate interval': '120'}
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
    photo_interval = general_conf.getint('photo interval')
    climate_interval = general_conf.getint('climate interval')

    # catch signals for clean exit
    watcher = KillWatcher()

    # connect relays module and restart camera
    camera = gpiozero.DigitalOutputDevice(pin=2, active_high=True)
    restart_camera()

    # connect temperature sensor
    sensor = Adafruit_DHT.DHT11
    sensor_pin = 4

    create_database()
    main_loop()

