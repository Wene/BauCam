#!/usr/bin/env python3

import sqlite3
import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt


class DB:
    def __init__(self):
        self.conn = sqlite3.connect('baucam.db')

    def __del__(self):
        self.conn.close()

    def get_climate(self):
        cur = self.conn.cursor()
        cur.execute('SELECT "raspi_time", "humidity", "temperature" from climate '
                    'WHERE "humidity" NOT NULL AND "temperature" NOT NULL ORDER BY "id";')
        result = cur.fetchall()
        return result


if '__main__' == __name__:
    db = DB()
    all_entries = db.get_climate()
    del db
    fig = plt.figure()
    ax = fig.add_subplot()
    ax.plot(all_entries)
    plt.show()