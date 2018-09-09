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
        out_bytes = subprocess.run(['gphoto2', '--capture-image-and-download'], timeout=20,
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
        print('Timeout while taking a photo...', flush=True)
    except Exception as e:
        print('Unknown exception:', flush=True)
        print(type(e), flush=True)
        print(e, flush=True)


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


def remote_archive():
    conn = sqlite3.connect(database_path)
    cur = conn.cursor()
    cur.execute('SELECT "rowid", "name" FROM "files" '
                'WHERE "remote_copy" = 0 AND "local_copy" = 1;')
    rows = cur.fetchall()
    copies = []
    for rowid, name in rows:
        # TODO: do the actual copying
        if int(rowid) % 2:
            copies.append((rowid, ))
    # for executemany() the iterable must contain tuples even if there is only one element in it.
    cur.executemany('UPDATE "files" SET "remote_copy" = 1 WHERE "rowid" = ?;', copies)

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
    camera_error = 0

    night_count = 0
    while True:
        now = datetime.now()

        # quit cleanly after receiving kill signal
        if watcher.kill_now:
            print('quitting...', flush=True)
            break

        # check if now is the time to take a photo
        photo_now = False
        if watcher.shoot:
            photo_now = True
            print('taking photo on SIGUSR1 trigger', flush=True)
            watcher.shoot = False

        if now >= last_photo + photo_interval:
            # increase last photo time by interval or set it to now if there is more than one delay between then and now
            last_photo += photo_interval
            if last_photo < now - photo_interval:
                last_photo = now

            if day_start < now.time() < day_end:
                night_count = 0 # it's day: reset night counter
                photo_now = True
                print('taking photo at day', flush=True)
            else:   # it's night: skip interval if not multiple of night_factor
                night_count += 1
                if 0 == night_count % night_factor:
                    photo_now = True
                    print('taking night photo at {}. interval'.format(night_count), flush=True)
                else:
                    print('no photo on {}. interval at night'.format(night_count), flush=True)

        if camera_error and now >= last_photo + timedelta(seconds=camera_error * 30):
            print('taking a rescue photo after {} failures'.format(camera_error), flush=True)
            photo_now = True

        # take photo if it's time to take a photo
        if photo_now:
            success = take_photo(capture_path, local_path, now)
            if success:
                camera_error = 0
            else:
                camera_error += 1
            if camera_error > 3:
                print('rebooting everything')
                subprocess.run(['sudo', 'reboot'])  # works only on systems with sudo without password (RasPi)
                sys.exit('reboot triggered')
            if camera_error > 2:
                print('rebooting camera', flush=True)
                restart_camera()
            if camera_error > 0:
                print('failure while photo taking. The system will be rebooted '
                      'after {} further failures.'.format(4 - camera_error), flush=True)

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
    #remote_archive()
