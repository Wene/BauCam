#!/usr/bin/env python3
import configparser
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
old_cur.execute('SELECT "rowid", "raspi_time", "humidity", "temperature" FROM "climate"')
climate_rows = old_cur.fetchall()
new_conn.executemany('INSERT INTO "climate" ("id", "raspi_time", "humidity", "temperature") VALUES (?, ?, ?, ?)',
                     climate_rows)
