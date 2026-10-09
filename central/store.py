"""Durable configuration and counts. Camera passwords never enter this database."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sqlite3
import uuid

# Staff: suppress duplicate crossings within this window (seconds).
# A staff member walking in-then-out is two distinct events; same direction
# within the window is treated as a phantom re-trigger and dropped.
STAFF_COOLDOWN_SECONDS = 15

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
                    created_at TEXT NOT NULL, zone_mode INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS crossings (
                    id TEXT PRIMARY KEY, camera_id TEXT NOT NULL REFERENCES cameras(id),
                    run_id TEXT NOT NULL, track_id INTEGER NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ("IN","OUT")),
                    observed_at TEXT NOT NULL, category TEXT NOT NULL DEFAULT "visitor",
                    staff_id TEXT);
                CREATE INDEX IF NOT EXISTS crossing_time ON crossings(observed_at, camera_id);
                CREATE TABLE IF NOT EXISTS camera_log (
                    id INTEGER PRIMARY KEY, camera_id TEXT NOT NULL REFERENCES cameras(id),
                    state TEXT NOT NULL, at TEXT NOT NULL);
            ''')
            # Migrations for existing databases
            cols = [col[1] for col in db.execute("PRAGMA table_info(cameras)").fetchall()]
            if "zone_mode" not in cols:
                db.execute("ALTER TABLE cameras ADD COLUMN zone_mode INTEGER NOT NULL DEFAULT 0")
            xcols = [col[1] for col in db.execute("PRAGMA table_info(crossings)").fetchall()]
            if "staff_id" not in xcols:
                db.execute("ALTER TABLE crossings ADD COLUMN staff_id TEXT")
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
        if not ref:
            raise ValueError('Camera stream URL, RTSP link, device index (e.g. 0), or secret name is required.')
        is_secret_name = bool(re.fullmatch(f'MAGGPIE_CAMERA_[A-Z0-9_]{1,60}', ref))
        is_direct_source = ref.lower().startswith(('rtsp://', 'rtsps://', 'http://', 'https://')) or ref.isdigit() or Path(ref).is_file()
        if not (is_secret_name or is_direct_source):
            raise ValueError('Provide a valid RTSP/HTTP stream URL, webcam index (e.g. 0), video file path, or secret name (e.g. MAGGPIE_CAMERA_ENTRY).')
        if axis not in ('horizontal', 'vertical') or not .1 <= position <= .9:
            raise ValueError('Invalid counting line.')
        direction = data.get('in_positive', True)
        if not isinstance(direction, bool):
            raise ValueError('Direction must be boolean.')
        zone_mode = int(bool(data.get('zone_mode', False)))
        camera_id = uuid.uuid4().hex
        with closing(self.connect()) as db, db:
            db.execute('INSERT INTO cameras VALUES (?,?,?,?,?,?,?,0,?,?)',
                       (camera_id, showroom, name, ref, axis, position, int(direction), utc_now(), zone_mode))
        return self.camera(camera_id)

    def delete_camera(self, camera_id):
        with closing(self.connect()) as db, db:
            db.execute('DELETE FROM crossings WHERE camera_id=?', (camera_id,))
            db.execute('DELETE FROM camera_log WHERE camera_id=?', (camera_id,))
            db.execute('DELETE FROM cameras WHERE id=?', (camera_id,))

    def set_enabled(self, camera_id, enabled):
        self.camera(camera_id)
        with closing(self.connect()) as db, db:
            db.execute('UPDATE cameras SET enabled=? WHERE id=?', (int(enabled), camera_id))

    def set_zone_mode(self, camera_id, zone_mode):
        self.camera(camera_id)
        with closing(self.connect()) as db, db:
            db.execute('UPDATE cameras SET zone_mode=? WHERE id=?', (int(bool(zone_mode)), camera_id))

    def set_line(self, camera_id, axis, position, in_positive):
        self.camera(camera_id)
        if axis not in ('horizontal', 'vertical') or not .1 <= position <= .9 or not isinstance(in_positive, bool):
            raise ValueError('Invalid counting line.')
        with closing(self.connect()) as db, db:
            db.execute('UPDATE cameras SET axis=?,position=?,in_positive=? WHERE id=?',
                       (axis,position,int(in_positive),camera_id))

    def record(self, camera_id, run_id, events, at):
        """Persist crossing events with uniqueness enforcement.

        Staff deduplication: the same staff_id crossing in the same direction
        within STAFF_COOLDOWN_SECONDS is silently dropped — this prevents
        phantom re-triggers from a staff member lingering near the line.
        Visitor deduplication (same direction within 60 s) is handled upstream
        in the CameraWorker before this method is called.
        """
        if not events:
            return
        with closing(self.connect()) as db, db:
            for e in events:
                staff_id = e.get('staff_id') or None
                category = e.get('category', 'visitor')
                direction = e['direction']

                # Staff uniqueness gate: drop crossing if same staff_id crossed
                # same direction recently in this camera.
                if staff_id and category == 'staff':
                    recent = db.execute(
                        '''SELECT observed_at FROM crossings
                           WHERE camera_id=? AND staff_id=? AND direction=?
                           ORDER BY observed_at DESC LIMIT 1''',
                        (camera_id, staff_id, direction)
                    ).fetchone()
                    if recent:
                        last_dt = datetime.fromisoformat(recent[0])
                        now_dt = datetime.fromisoformat(at)
                        # Make both tz-aware for safe subtraction
                        if last_dt.tzinfo is None:
                            last_dt = last_dt.replace(tzinfo=timezone.utc)
                        if now_dt.tzinfo is None:
                            now_dt = now_dt.replace(tzinfo=timezone.utc)
                        gap = (now_dt - last_dt).total_seconds()
                        if 0 <= gap < STAFF_COOLDOWN_SECONDS:
                            continue  # duplicate — skip

                db.execute(
                    'INSERT INTO crossings VALUES (?,?,?,?,?,?,?,?)',
                    (uuid.uuid4().hex, camera_id, run_id,
                     e['track_id'], direction, at, category, staff_id)
                )

    def log(self, camera_id, state):
        with closing(self.connect()) as db, db:
            try:
                db.execute('INSERT INTO camera_log(camera_id,state,at) VALUES (?,?,?)',
                           (camera_id, state, utc_now()))
            except sqlite3.IntegrityError:
                # Camera may have been deleted while worker was terminating
                pass

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

    def staff_crossings(self, limit=100):
        with closing(self.connect()) as db:
            rows = db.execute('''
                SELECT x.id, x.camera_id, c.name as camera_name, c.showroom, x.direction,
                       x.observed_at, x.category, x.staff_id,
                       CASE WHEN x.staff_id = 'uniform_staff' THEN 'Uniform Matched'
                            ELSE COALESCE(s.name, 'Enrolled Staff') END as staff_name
                FROM crossings x
                JOIN cameras c ON x.camera_id = c.id
                LEFT JOIN staff s ON x.staff_id = s.id
                WHERE x.category = 'staff'
                ORDER BY x.observed_at DESC
                LIMIT ?
            ''', (limit,)).fetchall()
            return [dict(r) for r in rows]

    def all_crossings(self, limit=100, camera_id=None):
        with closing(self.connect()) as db:
            query = '''
                SELECT x.id, x.camera_id, c.name as camera_name, c.showroom, x.direction,
                       x.observed_at, x.category, x.staff_id,
                       CASE WHEN x.staff_id = 'uniform_staff' THEN 'Uniform Matched'
                            WHEN x.category = 'staff' THEN COALESCE(s.name, 'Enrolled Staff')
                            ELSE NULL END as staff_name
                FROM crossings x
                JOIN cameras c ON x.camera_id = c.id
                LEFT JOIN staff s ON x.staff_id = s.id
            '''
            params = []
            if camera_id:
                query += ' WHERE x.camera_id = ?'
                params.append(camera_id)
            query += ' ORDER BY x.observed_at DESC LIMIT ?'
            params.append(limit)
            rows = db.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]
