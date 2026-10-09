"""Persistence for showroom uniform color histogram profiles in SQLite."""
from contextlib import closing
import json
import uuid
import cv2
import numpy as np

from central.store import utc_now


class UniformStore:
    def __init__(self, store):
        self.store = store
        with closing(store.connect()) as db, db:
            db.execute('''
                CREATE TABLE IF NOT EXISTS uniform_profiles (
                    id TEXT PRIMARY KEY,
                    showroom TEXT NOT NULL,
                    label TEXT NOT NULL,
                    histogram TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            ''')
            db.execute('CREATE INDEX IF NOT EXISTS idx_uniform_showroom ON uniform_profiles(showroom)')

    def register(self, showroom: str, label: str, sample_frames: list):
        if not showroom.strip() or not label.strip():
            raise ValueError('Showroom and label must not be empty.')
        if not sample_frames:
            raise ValueError('At least one sample frame is required.')

        hists = []
        for img in sample_frames:
            if img is None or img.size == 0:
                continue
            h, w = img.shape[:2]
            upper_crop = img[:max(1, int(h * 0.45)), :]
            hsv = cv2.cvtColor(upper_crop, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1, 2], None, [32, 32, 32], [0, 180, 0, 256, 0, 256])
            cv2.normalize(hist, hist, alpha=1.0, norm_type=cv2.NORM_L2)
            hists.append(hist)

        if not hists:
            raise ValueError('No valid image data to compute uniform histogram.')

        avg_hist = np.mean(hists, axis=0)
        cv2.normalize(avg_hist, avg_hist, alpha=1.0, norm_type=cv2.NORM_L2)

        encoded = json.dumps(avg_hist.tolist())
        profile_id = uuid.uuid4().hex
        with closing(self.store.connect()) as db, db:
            # Delete existing with same showroom + label to upsert
            db.execute('DELETE FROM uniform_profiles WHERE showroom=? AND label=?', (showroom.strip(), label.strip()))
            db.execute('INSERT INTO uniform_profiles VALUES (?,?,?,?,?)',
                       (profile_id, showroom.strip(), label.strip(), encoded, utc_now()))
        return profile_id

    def gallery(self, showroom: str) -> list[tuple[str, np.ndarray]]:
        with closing(self.store.connect()) as db:
            rows = db.execute('SELECT label, histogram FROM uniform_profiles WHERE showroom=?',
                              (showroom.strip(),)).fetchall()
        result = []
        for r in rows:
            arr = np.array(json.loads(r['histogram']), dtype=np.float32)
            result.append((r['label'], arr))
        return result

    def list(self, showroom: str | None = None):
        with closing(self.store.connect()) as db:
            if showroom:
                rows = db.execute('SELECT id, showroom, label, created_at FROM uniform_profiles WHERE showroom=?',
                                  (showroom.strip(),)).fetchall()
            else:
                rows = db.execute('SELECT id, showroom, label, created_at FROM uniform_profiles ORDER BY created_at').fetchall()
            return [dict(r) for r in rows]

    def delete(self, showroom: str, label: str):
        with closing(self.store.connect()) as db, db:
            db.execute('DELETE FROM uniform_profiles WHERE showroom=? AND label=?', (showroom.strip(), label.strip()))
