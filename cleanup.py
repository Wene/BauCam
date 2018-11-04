#!/usr/bin/env python3

import argparse
import configparser
import os
import sqlite3
import sys, errno

parser = argparse.ArgumentParser(description='cleanup unwanted pictures from local and remote storage and the database')
parser.add_argument('-d', '--delete', help='actually perform the delete action', action='store_true')
parser.add_argument('-l', '--list', help='show the list of files to delete', action='store_true')
args = parser.parse_args()

print('---   ---   ---')
print(args)
print('---   ---   ---')

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

if args.list:
    print("List is active")

if args.delete:
    print("Delete is active")
