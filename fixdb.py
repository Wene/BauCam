#!/usr/bin/env python3
import configparser
from datetime import datetime
import os
import sqlite3

conf = configparser.ConfigParser()
conf.read('BauCam.conf')
general_conf = conf['general']
old_database_path = os.path.expanduser(general_conf.get('database path'))

base, ext = os.path.splitext(old_database_path)
new_database_path = base + '-tmp' + ext

old_conn = sqlite3.connect(old_database_path)
old_cur = old_conn.cursor()

new_conn = sqlite3.connect(new_database_path)
new_cur = new_conn.cursor()

new_cur.execute('CREATE TABLE IF NOT EXISTS "images" ("id" INTEGER PRIMARY KEY, "raspi_time" TEXT, "camera_time" TEXT, '
                '"gphoto_output" TEXT, "to_delete" INTEGER DEFAULT 0);')
new_cur.execute('CREATE TABLE IF NOT EXISTS "files" ("id" INTEGER PRIMARY KEY, "images_id" INTEGER NOT NULL, '
                '"name" TEXT NOT NULL, "local_copy" INTEGER NOT NULL DEFAULT (1), '
                '"remote_copy" INTEGER NOT NULL DEFAULT (0));')
new_cur.execute('CREATE TABLE IF NOT EXISTS "tags" ("id" INTEGER PRIMARY KEY, "images_id" INTEGER NOT NULL, '
                '"name" TEXT NOT NULL, "value" TEXT);')
new_cur.execute('CREATE TABLE IF NOT EXISTS "climate" ("id" INTEGER PRIMARY KEY, "raspi_time" TEXT, '
                '"humidity" REAL, "temperature" REAL);')

# copy climate info - without references
old_cur.execute('SELECT "raspi_time", "humidity", "temperature" FROM "climate" ORDER BY "rowid";')
climate_rows = old_cur.fetchall()
new_cur.executemany('INSERT INTO "climate" ("raspi_time", "humidity", "temperature") VALUES (?, ?, ?);',
                     climate_rows)

# copy images and create new references
old_cur.execute('SELECT "raspi_time", "camera_time", "gphoto_output", "to_delete" FROM "images" ORDER BY "rowid";')
images_rows = old_cur.fetchall()
ids = dict()
for row in images_rows:
    timestamp = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S.%f')
    key = timestamp.strftime('%Y-%m-%d_%H-%M-%S')
    new_cur.execute('INSERT INTO "images" ("raspi_time", "camera_time", "gphoto_output", "to_delete") '
                    'VALUES (?, ?, ?, ?);', row)
    new_cur.execute('SELECT last_insert_rowid();')
    row_id = new_cur.fetchone()[0]
    ids[key] = row_id

old_cur.execute('SELECT "name", "local_copy", "remote_copy" FROM "files";')
files = old_cur.fetchall()
for record in files:
    key = record[0][5:24]
    if key in ids:
        foreign_key = ids[key]
    else:
        print('ID for key {} not found', key)
        foreign_key = 0
    new_cur.execute('INSERT INTO "files" ("images_id", "name", "local_copy", "remote_copy") '
                    'VALUES (?, ?, ?, ?);', (foreign_key,) + record)  # comma needed after one record for a valid tuple

old_conn.close()
new_conn.commit()
new_conn.close()

