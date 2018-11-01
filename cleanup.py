#!/usr/bin/env python3

import argparse

parser = argparse.ArgumentParser(description='cleanup unwanted pictures from local and remote storage and the database')
parser.add_argument('-d', '--delete', help='actually perform the delete action', action='store_true')
parser.add_argument('-l', '--list', help='show the list of files to delete', action='store_true')
args = parser.parse_args()

print('---   ---   ---')
print(args)
print(args.delete)