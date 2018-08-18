#!/usr/bin/env python3

import os
import signal
import subprocess
import exifread
import configparser
import sqlite3
from time import sleep
from datetime import datetime, timedelta, time
import gpiozero
import sys
import Adafruit_DHT


# TODO: copy data to remote location

class KillWatcher:
    kill_now = False
    shoot = False

    def __init__(self):
        signal.signal(signal.SIGTERM, self.handler_kill)
        signal.signal(signal.SIGINT, self.handler_kill)
        signal.signal(signal.SIGUSR1, self.handler_usr1)

    def handler_kill(self, signum, frame):
        self.kill_now = True

    def handler_usr1(self, signum, frame):
        self.shoot = True


def take_photo(capture_path, local_path, now):
    os.chdir(capture_path)
    pic_name = image_prefix + now.strftime('%Y-%m-%d_%H-%M-%S')

    # clean up the directory
    files = os.listdir()
    for file_name in files:
        os.remove(file_name)

    try:
        out_bytes = subprocess.run(['gphoto2', '--capture-image-and-download'], timeout=15,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout
        output = str(out_bytes, 'utf-8')
        final_names = [None]
        files = os.listdir()
        for file_name in files:
            base, ext = os.path.splitext(file_name)
            new_name = pic_name + ext
            os.rename(file_name, os.path.join(local_path, new_name))
            if '.jpg' == ext.lower() or '.jpeg' == ext.lower():
                final_names[0] = new_name
            else:
                final_names.append(new_name)

        if final_names[0] is not None:
            jpeg_path = os.path.join(local_path, final_names[0])
            exif_tags, cam_time = extract_exif(jpeg_path)
            store_exif_in_database(now, output, cam_time=cam_time, file_names=final_names, exif_tags=exif_tags)
            return True
        else:
            store_exif_in_database(now, output)
            return False

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
    conn = sqlite3.connect(database_path)
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS "images" ("raspi_time" TEXT, "camera_time" TEXT, "gphoto_output" TEXT);')
    cur.execute('CREATE TABLE IF NOT EXISTS "files" ("images_rowid" INTEGER NOT NULL, "name" TEXT NOT NULL, '
                '"local_copy" INTEGER NOT NULL DEFAULT (1), "remote_copy" INTEGER NOT NULL DEFAULT (0));')
    cur.execute('CREATE TABLE IF NOT EXISTS "tags" ("images_rowid" INTEGER NOT NULL, '
                '"name" TEXT NOT NULL, "value" TEXT);')
    cur.execute('CREATE TABLE IF NOT EXISTS "climate" ("raspi_time" TEXT, "humidity" REAL, "temperature" REAL);')
    conn.commit()
    conn.close()


def store_exif_in_database(timestamp, output, cam_time=None, file_names=[], exif_tags={}):
    # store data in database
    conn = sqlite3.connect(database_path)
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


def measure_and_store_climate(timestamp):
    # measure the climate data
    humidity, temperature = Adafruit_DHT.read(sensor, sensor_pin)

    # store data in database
    conn = sqlite3.connect(database_path)
    cur = conn.cursor()
    cur.execute('INSERT INTO climate (raspi_time, humidity, temperature) '
                'VALUES (?, ?, ?)', (timestamp, humidity, temperature))
    conn.commit()
    conn.close()


def restart_camera():
    camera.off()
    sleep(5)
    camera.on()
    sleep(5)


def main_loop():
    last_photo = datetime.now() - photo_interval - timedelta(seconds=2)
    last_climate = datetime.now() - climate_interval - timedelta(seconds=2)
    no_photo_taken = 0

    night_count = 0
    while True:
        now = datetime.now()

        # quit cleanly after receiving kill signal
        if watcher.kill_now:
            print('quitting...')
            break

        # check if now is the time to take a photo
        photo_now = False
        if watcher.shoot:
            photo_now = True
            watcher.shoot = False

        if now >= last_photo + photo_interval:
            # increase last photo time by interval or set it to now if there is more than one delay between then and now
            last_photo += photo_interval
            if last_photo < now - photo_interval:
                last_photo = now

            if day_start < now.time() < day_end:
                night_count = 0 # it's day: reset night counter
                photo_now = True
            else:   # it's night: skip interval if not multiple of night_factor
                night_count += 1
                if 0 == night_count % night_factor:
                    photo_now = True

        # take photo it's time to take a photo
        if photo_now:
            success = take_photo(capture_path, local_path, now)
            if success:
                no_photo_taken = 0
            else:
                no_photo_taken += 1
                last_photo = last_photo - photo_interval + timedelta(seconds=no_photo_taken * 30)
            if no_photo_taken > 3:
                print('rebooting everything')
                subprocess.run(['sudo', 'reboot'])  # works only on systems with sudo without password (RasPi)
                sys.exit('reboot triggered')
            if no_photo_taken > 2:
                print('rebooting camera')
                restart_camera()
            if no_photo_taken > 0:
                print('system will be rebooted after', 4 - no_photo_taken, 'failures.')

        if now >= last_climate + climate_interval:

            # increase last climate time by interval or set it to now if there is more than one delay between then and now
            last_climate += climate_interval
            if last_climate < now - climate_interval:
                    last_climate = now

            measure_and_store_climate(now)

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
                           'database path': '~/BauCam/baucam.db',
                           'photo interval': '600',
                           'night factor': '6',
                           'climate interval': '120',
                           'image prefix': 'img_',
                           'day start': '6:00',
                           'day end': '21:00'}
        with open('BauCam.conf', 'w') as f:
            conf.write(f)
    general_conf = conf['general']
    # read all paths and create them if they don't exist
    capture_path = os.path.expanduser(general_conf.get('capture path'))
    local_path = os.path.expanduser(general_conf.get('local path'))
    remote_path = os.path.expanduser(general_conf.get('remote path'))
    database_path = os.path.expanduser(general_conf.get('database path'))
    if not os.path.isdir(capture_path):
        os.makedirs(capture_path)
    if not os.path.isdir(local_path):
        os.makedirs(local_path)
    if not os.path.isdir(remote_path):
        os.makedirs(remote_path)
    photo_interval = timedelta(seconds=general_conf.getint('photo interval'))
    climate_interval = timedelta(seconds=general_conf.getint('climate interval'))
    night_factor = general_conf.getint('night factor')
    image_prefix = general_conf.get('image prefix')
    day_start = datetime.strptime(general_conf.get('day start'), '%H:%M').time()
    day_end = datetime.strptime(general_conf.get('day end'), '%H:%M').time()

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

