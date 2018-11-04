#!/usr/bin/env python3

import argparse
import configparser
import os
import sqlite3
import sys, errno

parser = argparse.ArgumentParser(description='cleanup unwanted pictures from local and remote storage and the database')
parser.add_argument('-l', '--list', help='show the list of files to delete', action='store_true')
parser.add_argument('-d', '--delete', help='actually perform the delete action', action='store_true')
parser.add_argument('-c', '--clean', help='clean up records without files', action='store_true')
parser.add_argument('-v', '--vacuum', help='vacuum the database to release free space', action='store_true')
args = parser.parse_args()

conf = configparser.ConfigParser()
if os.path.isfile('BauCam.conf'):
    conf.read('BauCam.conf')
    general_conf = conf['general']
    database_path = os.path.expanduser(general_conf.get('database path'))
else:
    print("BauCam.conf not found!")
    sys.exit(errno.EACCES)

if os.path.isfile(database_path):
    conn = sqlite3.connect(database_path)
    cur = conn.cursor()
else:
    print("Database not found!")
    sys.exit(errno.EACCES)

cur.execute('SELECT "i"."rowid", "f"."rowid", "f"."name", "f"."local_copy", "f"."remote_copy" '
            'FROM "files" AS "f", "images" AS "i" '
            'WHERE "i"."rowid" = "f"."images_rowid" AND "i"."to_delete" = 1;')
delete_rows = cur.fetchall()
cur.execute('SELECT "rowid" FROM images WHERE rowid NOT IN (SELECT "images_rowid" FROM "files");')
clean_rows = cur.fetchall()

if args.list:
    for i_rowid, f_rowid, name, local, remote in delete_rows:
        print(name)

if args.delete:
    image_rows = list()
    file_rows = list()
    for i_rowid, f_rowid, name, local, remote in delete_rows:
        if i_rowid not in image_rows:
            image_rows.append(i_rowid)
        file_rows.append(f_rowid)
        if remote:
            pass    # TODO: delete remote files if still existing
        if local:
            pass    # TODO: delete local files if still existing
        # TODO: delete SQL records in files and images

if args.clean:
    numbers = list()
    for id, in clean_rows:
        numbers.append(id)
    query = 'DELETE FROM "images" WHERE "rowid" in (  '
    for i in numbers:
        query += '?, '
    query = query[:-2] + ');'
    cur.execute(query, numbers)

conn.commit()

if args.vacuum:
    conn.execute('VACUUM;')

conn.close()