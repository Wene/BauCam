#!/usr/bin/env python3

import os
import shutil
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
        return False
    except Exception as e:
        print('Unknown exception:', flush=True)
        print(type(e), flush=True)
        print(e, flush=True)
        return False


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
    # establish connection to DB
    conn = sqlite3.connect(database_path)
    cur = conn.cursor()

    start_time = datetime.now() # remember current time
    no_timeout = True

    # get all names of only local files
    cur.execute('SELECT "rowid", "name" FROM "files" '
                'WHERE "remote_copy" = 0 AND "local_copy" = 1;')
    rows = cur.fetchall()

    # work through all files in the list and copy them to remote_path
    for rowid, name in rows:

        # copying many files could take a long time - break here if this took longer than a photo_interval
        if start_time + photo_interval <= datetime.now():
            print('Timeout while copying files', flush=True)
            no_timeout = False
            break

        # check if remote canary.txt is available
        if not os.path.exists(os.path.join(remote_path, 'canary.txt')):
            print('canary.txt on remote path not found - archiving omitted', flush=True)
            break

        # copy the current file and update DB including error handling
        try:
            shutil.copy2(os.path.join(local_path, name), remote_path)
            cur.execute('UPDATE "files" SET "remote_copy" = 1 WHERE "rowid" = ?;', [rowid])
        except FileNotFoundError as e:
            print('Source file not found. Setting local_copy to 0.', e, flush=True)
            cur.execute('UPDATE "files" SET "local_copy" = 0 WHERE "rowid" = ?;', [rowid])
        except PermissionError as e:
            print('Permission denied:', e, flush=True)
            break
        except OSError as e:
            print('OS Error:', e, flush=True)
            break
        except Exception as e:
            print('Unhandled exception:', flush=True)
            print(type(e), flush=True)
            print(e, flush=True)
            break

    # get all names of files in both locations
    cur.execute('SELECT "rowid", "name" FROM "files" '
                'WHERE "remote_copy" = 1 AND "local_copy" = 1;')
    rows = cur.fetchall()

    if no_timeout:  # only continue if no timeout occurred before
        for rowid, name in rows:

            # break here if this took longer than a photo_interval
            if start_time + photo_interval <= datetime.now():
                print('Timeout while deleting files', flush=True)
                no_timeout = False
                break

            # get free space on local_path
            stat = os.statvfs(local_path)
            space = stat.f_bavail * stat.f_frsize

            # break as soon as there is enough free space
            if space > min_free_space:
                break

            # delete current file including error handling
            try:
                os.remove(os.path.join(local_path, name))
                cur.execute('UPDATE "files" SET "local_copy" = 0 WHERE "rowid" = ?;', [rowid])
            except FileNotFoundError as e:
                print('File not found while deleting. Setting local_copy to 0.', e, flush=True)
                cur.execute('UPDATE "files" SET "local_copy" = 0 WHERE "rowid" = ?;', [rowid])
            except Exception as e:
                print('Unhandled exception:', flush=True)
                print(type(e), flush=True)
                print(e, flush=True)
                break

    # close DB connection
    conn.commit()
    conn.close()

    # create a backup of the db if enough time left
    # ToDo: remove old backups from time to time
    if no_timeout and os.path.exists(os.path.join(remote_path, 'canary.txt')):
        try:
            date_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            backup_path = os.path.join(remote_path, image_prefix + 'dbBackup_' + date_str + '.db')
            shutil.copy2(database_path, backup_path)
        except FileNotFoundError as e:
            print('Source DB file not found.', e, flush=True)
        except PermissionError as e:
            print('Permission denied:', e, flush=True)
        except OSError as e:
            print('OS Error:', e, flush=True)
        except Exception as e:
            print('Unhandled exception:', flush=True)
            print(type(e), flush=True)
            print(e, flush=True)


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

    interval_count = 1
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

            factor = 1
            weekday = day = True
            if not day_start < now.time() < day_end:
                factor *= night_factor
                day = False
            if now.weekday() in weekend_days:
                factor *= weekend_factor
                weekday = False
            if weekday and day:
                interval_count = 1  # it's day during the week: reset counter
            if 0 == interval_count % factor:
                photo_now = True
                print('taking photo at {}. interval'.format(interval_count), flush=True)
            else:
                print('no photo at {}. interval of {}'.format(interval_count, factor), flush=True)
            interval_count += 1

        if camera_error and now >= last_photo + timedelta(seconds=camera_error * 30):
            print('taking a rescue photo after {} failures'.format(camera_error), flush=True)
            photo_now = True

        # take photo if it's time to take a photo
        if photo_now:
            success = take_photo(capture_path, local_path, now)
            if success:
                camera_error = 0
                # use the time after a successful photo to archive files
                remote_archive()
            else:
                if day:
                    camera_error += 1   # count errors only at day - avoid reboots over night
                else:
                    camera_error = 0    # reset error counter at night to avoid endless retries
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
    # create new default config if it doesn't exist
    changed = False
    if 'general' not in conf.sections():
        conf['general'] = {}
        changed = True
    general_conf = conf['general']
    if general_conf.get('capture path') is None:
        general_conf['capture path'] = '/tmp/BauCam'
        changed = True
    if general_conf.get('local path') is None:
        general_conf['local path'] = '~/BauCam/images'
        changed = True
    if general_conf.get('remote path') is None:
        general_conf['remote path'] = '~/BauCam/remote'
        changed = True
    if general_conf.get('database path') is None:
        general_conf['database path'] = '~/BauCam/baucam.db'
        changed = True
    if general_conf.get('photo interval') is None:
        general_conf['photo interval'] = '600'
        changed = True
    if general_conf.get('night factor') is None:
        general_conf['night factor'] = '6'
        changed = True
    if general_conf.get('climate interval') is None:
        general_conf['climate interval'] = '120'
        changed = True
    if general_conf.get('image prefix') is None:
        general_conf['image prefix'] = 'img_'
        changed = True
    if general_conf.get('day start') is None:
        general_conf['day start'] = '6:00'
        changed = True
    if general_conf.get('day end') is None:
        general_conf['day end'] = '21:00'
        changed = True
    if general_conf.get('free space') is None:
        general_conf['free space'] = str(1024 * 1024 * 1024)
        changed = True
    if general_conf.get('weekend days') is None:
        general_conf['weekend days'] = '5 6'
        changed = True
    if general_conf.get('weekend factor') is None:
        general_conf['weekend factor'] = '12'
        changed = True

    if changed:
        with open('BauCam.conf', 'w') as f:
            conf.write(f)

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

    # read other configuration data
    photo_interval = timedelta(seconds=general_conf.getint('photo interval'))
    climate_interval = timedelta(seconds=general_conf.getint('climate interval'))
    night_factor = general_conf.getint('night factor')
    image_prefix = general_conf.get('image prefix')
    day_start = datetime.strptime(general_conf.get('day start'), '%H:%M').time()
    day_end = datetime.strptime(general_conf.get('day end'), '%H:%M').time()
    min_free_space = general_conf.getint('free space')
    weekend_days = [int(x) for x in general_conf.get('weekend days').split()]
    weekend_factor = general_conf.getint('weekend factor')

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
