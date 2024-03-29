import json
import os
import shutil
from datetime import datetime as dt
from threading import Lock

from utils.emailer import send_notification
from app.site import j2env
from app.utils.config import Config

lock = Lock()


class DayReport:
    def __init__(self, agency: str):
        self.agency = agency
        with lock:
            try:
                self.dump(self.init(self.load()))
            except:  # noqa
                if os.path.exists(Config.dayreport_file):
                    os.remove(Config.dayreport_file)
                self.dump(self.init({}))

    def init(self, data):
        if self.agency not in data:
            data[self.agency] = {'exceptions': [], 'articles': 0, 'headlines': 0, 'updated': 0}
        return data

    @staticmethod
    def load():
        with open(Config.dayreport_file, 'rt') as file:
            return json.load(file)

    @staticmethod
    def dump(data):
        with open(Config.dayreport_file, 'wt') as file:
            json.dump(data, file, indent=4)

    def add_exception(self, message: str, traceback: str):
        with lock:
            data = self.load()
            data[self.agency]['exceptions'].append({'msg': message, 'tb': traceback, 'time': dt.now().isoformat()})
            self.dump(data)

    def articles(self, count: int):
        with lock:
            data = self.load()
            if not 'articles' in data[self.agency]:
                data[self.agency]['articles'] = 0
            data[self.agency]['articles'] += count
            self.dump(data)

    def headlines(self, count: int):
        with lock:
            data = self.load()
            if not 'headlines' in data[self.agency]:
                data[self.agency]['headlines'] = 0
            data[self.agency]['headlines'] += count
            self.dump(data)

    def updated(self, count: int):
        with lock:
            data = self.load()
            if not 'updated' in data[self.agency]:
                data[self.agency]['updated'] = 0
            data[self.agency]['updated'] += count
            self.dump(data)

    @staticmethod
    def report_turnover():
        with lock:
            data = DayReport.load()
            send_notification(j2env.get_template('dayreport.txt').render(data=data))
            shutil.move(Config.dayreport_file, Config.dayreport_file + dt.now().isoformat())
            DayReport.dump({})
