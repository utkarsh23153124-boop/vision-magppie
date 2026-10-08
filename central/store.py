"""Durable configuration and counts. Camera passwords never enter this database."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sqlite3
import uuid

IST = timezone(timedelta(hours=5, minutes=30))


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS cameras (
                    id TEXT PRIMARY KEY, showroom TEXT NOT NULL, name TEXT NOT NULL,
                    source_ref TEXT NOT NULL, axis TEXT NOT NULL, position REAL NOT NULL,
                    in_positive INTEGER NOT NULL, enabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS crossings (
                    id TEXT PRIMARY KEY, camera_id TEXT NOT NULL REFERENCES cameras(id),
                    run_id TEXT NOT NULL, track_id INTEGER NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('IN','OUT')),
                    observed_at TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'visitor');
                CREATE INDEX IF NOT EXISTS crossing_time ON crossings(observed_at, camera_id);
                CREATE TABLE IF NOT EXISTS camera_log (
                    id INTEGER PRIMARY KEY, camera_id TEXT NOT NULL REFERENCES cameras(id),
                    state TEXT NOT NULL, at TEXT NOT NULL);
            ''')
            db.commit()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def cameras(self):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute('SELECT * FROM cameras ORDER BY created_at')]

    def camera(self, camera_id):
        with closing(self.connect()) as db:
            row = db.execute('SELECT * FROM cameras WHERE id=?', (camera_id,)).fetchone()
            if row is None:
                raise ValueError('Camera not found.')
            return dict(row)

    def add_camera(self, data):
        showroom, name = str(data.get('showroom', '')).strip(), str(data.get('name', '')).strip()
        ref = str(data.get('source_ref', '')).strip()
        axis, position = data.get('axis', 'vertical'), float(data.get('position', .5))
        if not showroom or not name or max(len(showroom), len(name)) > 80:
            raise ValueError('Showroom and camera names must be 1–80 characters.')
        if not re.fullmatch(r'MAGGPIE_CAMERA_[A-Z0-9_]{1,60}', ref):
            raise ValueError('Use a server secret name such as MAGGPIE_CAMERA_DELHI_ENTRY.')
        if axis not in ('horizontal', 'vertical') or not .1 <= position <= .9:
            raise ValueError('Invalid counting line.')
        direction = data.get('in_positive', True)
        if not isinstance(direction, bool):
            raise ValueError('Direction must be boolean.')
        camera_id = uuid.uuid4().hex
        with closing(self.connect()) as db, db:
            db.execute('INSERT INTO cameras VALUES (?,?,?,?,?,?,?,0,?)',
                       (camera_id, showroom, name, ref, axis, position, int(direction), utc_now()))
        return self.camera(camera_id)

    def set_enabled(self, camera_id, enabled):
        self.camera(camera_id)
        with closing(self.connect()) as db, db:
            db.execute('UPDATE cameras SET enabled=? WHERE id=?', (int(enabled), camera_id))

    def set_line(self, camera_id, axis, position, in_positive):
        self.camera(camera_id)
        if axis not in ('horizontal', 'vertical') or not .1 <= position <= .9 or not isinstance(in_positive, bool):
            raise ValueError('Invalid counting line.')
        with closing(self.connect()) as db, db:
            db.execute('UPDATE cameras SET axis=?,position=?,in_positive=? WHERE id=?',
                       (axis,position,int(in_positive),camera_id))

    def record(self, camera_id, run_id, events, at):
        if not events:
            return
        with closing(self.connect()) as db, db:
            db.executemany('INSERT INTO crossings VALUES (?,?,?,?,?,?,?)',
                           [(uuid.uuid4().hex, camera_id, run_id, e['track_id'], e['direction'], at, e.get('category','visitor'))
                            for e in events])

    def log(self, camera_id, state):
        with closing(self.connect()) as db, db:
            db.execute('INSERT INTO camera_log(camera_id,state,at) VALUES (?,?,?)',
                       (camera_id, state, utc_now()))

    def report(self, date):
        start = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=IST)
        end = start + timedelta(days=1)
        with closing(self.connect()) as db:
            rows = db.execute('''SELECT c.id, c.showroom, c.name, x.direction, x.observed_at, x.category
                FROM cameras c LEFT JOIN crossings x ON c.id=x.camera_id
                  AND x.observed_at>=? AND x.observed_at<? ORDER BY c.created_at''',
                              (start.astimezone(timezone.utc).isoformat(),
                               end.astimezone(timezone.utc).isoformat())).fetchall()
            logs = [dict(r) for r in db.execute('''SELECT camera_id,state,at FROM camera_log
                WHERE at>=? AND at<? ORDER BY at DESC LIMIT 100''',
                    (start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()))]
        cameras, hours = {}, [{'hour': hour, 'entries': 0, 'exits': 0} for hour in range(24)]
        for row in rows:
            item = cameras.setdefault(row['id'], {'camera_id': row['id'], 'showroom': row['showroom'],
                                                  'name': row['name'], 'entries': 0, 'exits': 0, 'staff_excluded': 0})
            if row['direction']:
                if row['category'] == 'staff':
                    item['staff_excluded'] += 1
                    continue
                key = 'entries' if row['direction'] == 'IN' else 'exits'
                item[key] += 1
                hour = datetime.fromisoformat(row['observed_at']).astimezone(IST).hour
                hours[hour][key] += 1
        return {'date': date, 'timezone': 'Asia/Kolkata', 'cameras': list(cameras.values()),
                'hours': hours, 'connection_log': logs,
                'scope': 'Physical crossings; not unique visitors, groups or verified occupancy.'}
