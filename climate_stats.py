#!/usr/bin/env python3

import sqlite3
import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
from matplotlib.dates import date2num, DateFormatter
from datetime import datetime

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
        dates = []
        values = []
        for entry in result:
            date_str = entry[0]
            date = datetime.fromisoformat(date_str)
            date_num = date2num(date)
            dates.append(date_num)
            values.append(entry[1:])
        return dates, values


if '__main__' == __name__:
    db = DB()
    dates, values = db.get_climate()
    del db
    fig, ax = plt.subplots()
    ax.plot(dates, values)
    ax.set(xlabel='Date', ylabel='Value', title='Climate data')
    ax.xaxis.set_major_formatter(DateFormatter('%Y-%m-%d %H:%M'))
    plt.setp(ax.get_xticklabels(), rotation=45)
    plt.show()
