"""Consented, showroom-scoped staff face matching. No visitor identity database."""
from contextlib import closing
import json
import os
import uuid

from cryptography.fernet import Fernet
import cv2
import numpy as np

from vision.models import ROOT, verified
from central.store import utc_now

MODEL = ROOT / 'models' / 'face_recognition_sface_2021dec.onnx'
SHA256 = '0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79'


class StaffStore:
    def __init__(self, store, key):
        self.store, self.cipher = store, Fernet(key)
        with closing(store.connect()) as db, db:
            db.execute('''CREATE TABLE IF NOT EXISTS staff (
                id TEXT PRIMARY KEY, showroom TEXT NOT NULL, name TEXT NOT NULL,
                templates BLOB NOT NULL, consent_at TEXT NOT NULL)''')

    def add(self, showroom, name, embeddings, consent):
        if consent is not True:
            raise ValueError('Confirm staff consent before enrollment.')
        if not showroom.strip() or not name.strip() or max(len(showroom), len(name)) > 80:
            raise ValueError('Staff name and showroom must be 1–80 characters.')
        if not 1 <= len(embeddings) <= 10:
            raise ValueError('Use 1–10 clear photos of one consenting staff member.')
        staff_id = uuid.uuid4().hex
        encrypted = self.cipher.encrypt(json.dumps([v.tolist() for v in embeddings]).encode())
        with closing(self.store.connect()) as db, db:
            db.execute('INSERT INTO staff VALUES (?,?,?,?,?)',
                       (staff_id, showroom.strip(), name.strip(), encrypted, utc_now()))
        return staff_id

    def list(self):
        with closing(self.store.connect()) as db:
            return [dict(r) for r in db.execute('SELECT id,showroom,name,consent_at FROM staff')]

    def gallery(self, showroom):
        with closing(self.store.connect()) as db:
            if showroom and showroom.strip():
                rows = db.execute(
                    'SELECT id,templates FROM staff WHERE LOWER(TRIM(showroom))=LOWER(TRIM(?))',
                    (showroom.strip(),)
                ).fetchall()
                if not rows:
                    rows = db.execute('SELECT id,templates FROM staff').fetchall()
            else:
                rows = db.execute('SELECT id,templates FROM staff').fetchall()
        return [(row['id'], np.array(json.loads(self.cipher.decrypt(row['templates'])), dtype=np.float32))
                for row in rows]

    def delete(self, staff_id):
        with closing(self.store.connect()) as db, db:
            db.execute('DELETE FROM staff WHERE id=?', (staff_id,))


class Recognizer:
    def __init__(self):
        if not verified(MODEL, SHA256):
            raise ValueError('Staff model missing. Run python -m central.download_models.')
        self.model = cv2.FaceRecognizerSF.create(str(MODEL), '')

    def feature(self, image, row):
        vector = self.model.feature(self.model.alignCrop(image, row)).reshape(-1)
        return vector / max(float(np.linalg.norm(vector)), 1e-9)

    def enroll(self, image, detector):
        detector.faces(image)
        rows = detector.last_face_rows
        if rows is None or len(rows) != 1:
            raise ValueError('Each photo must contain exactly one clear face.')
        row = rows[0]
        if min(row[2:4]) < 80:
            raise ValueError('Face is too small. Upload a closer portrait.')
        crop = self.model.alignCrop(detector.last_face_image, row)
        if cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var() < 40:
            raise ValueError('Face photo is too blurry. Use a sharper photo.')
        return self.feature(detector.last_face_image, row)


from vision.uniform import UniformMatcher, FrequencySuppressor


class StaffMatcher:
    def __init__(self, staff_store, showroom, uniform_matcher=None, freq_suppressor=None):
        self.store, self.showroom = staff_store, showroom
        self.recognizer = Recognizer()
        self.matches = {}  # track_id -> (staff_id, hits, last_match_time)
        self.track_staff = {}  # track_id -> (staff_id, max_score, timestamp)
        self.uniform_matcher = uniform_matcher or UniformMatcher()
        self.freq_suppressor = freq_suppressor or FrequencySuppressor()

    def update(self, tracks, detector, now, frame=None):
        gallery = self.store.gallery(self.showroom)
        valid_ids = {staff_id for staff_id, _ in gallery}
        valid_ids.add('uniform_staff')
        active = {t.id for t in tracks}

        # Retain matched staff identity for active tracks
        self.matches = {k: v for k, v in self.matches.items() if k in active}
        self.track_staff = {k: v for k, v in self.track_staff.items() if k in active}

        rows = getattr(detector, 'last_face_rows', None)
        face_img = getattr(detector, 'last_face_image', None)
        if rows is not None and gallery and face_img is not None:
            height, width = face_img.shape[:2]
            candidates = {}
            for row in rows:
                if min(row[2:4]) < 18:
                    continue
                x, y = (row[0] + row[2] / 2) / width, (row[1] + row[3] / 2) / height
                # Associate face with track if center is in the upper 80% of body box
                owners = [t for t in tracks if t.observed and
                          (t.box[0] - 0.04) <= x <= (t.box[2] + 0.04) and
                          (t.box[1] - 0.04) <= y <= (t.box[1] + 0.80 * (t.box[3] - t.box[1]))]
                if len(owners) == 1:
                    candidates.setdefault(owners[0].id, []).append(row)

            for track_id, face_rows in candidates.items():
                best_face = max(face_rows, key=lambda r: r[2] * r[3])
                feature = self.recognizer.feature(face_img, best_face)
                ranked = sorted([(float(np.max(vectors @ feature)), staff_id) for staff_id, vectors in gallery], reverse=True)
                score, staff_id = ranked[0]
                # SFace cosine similarity threshold: 0.35 is standard for webcam / IP camera conditions
                if score >= 0.35:
                    prev = self.matches.get(track_id)
                    hits = (prev[1] + 1) if (prev and prev[0] == staff_id) else 1
                    self.matches[track_id] = (staff_id, hits, now)
                    self.track_staff[track_id] = (staff_id, score, now)

        # Secondary filter: Uniform color matching when frame is provided
        uniform_matcher = getattr(self, 'uniform_matcher', None)
        if frame is not None and uniform_matcher and uniform_matcher.profiles:
            for track in tracks:
                if track.id in self.track_staff:
                    continue
                is_match, conf = uniform_matcher.is_uniform_match(frame, track.box)
                if is_match:
                    self.matches[track.id] = ('uniform_staff', 2, now)
                    self.track_staff[track.id] = ('uniform_staff', conf, now)

    def is_staff(self, track_id, now):
        freq_suppressor = getattr(self, 'freq_suppressor', None)
        if freq_suppressor and freq_suppressor.is_frequent(track_id, now):
            return True
        if track_id in self.track_staff:
            return True
        match = self.matches.get(track_id)
        return bool(match and match[1] >= 1)

    def get_staff_id(self, track_id):
        if track_id in self.track_staff:
            return self.track_staff[track_id][0]
        if track_id in self.matches:
            return self.matches[track_id][0]
        return None
