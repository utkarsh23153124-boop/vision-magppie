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
        if not 1 <= len(embeddings) <= 5:
            raise ValueError('Use 1–5 clear photos of one consenting staff member.')
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
            rows = db.execute('SELECT id,templates FROM staff WHERE showroom=?', (showroom,)).fetchall()
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


class StaffMatcher:
    def __init__(self, staff_store, showroom):
        self.store, self.showroom = staff_store, showroom
        self.recognizer = Recognizer()
        self.matches = {}

    def update(self, tracks, detector, now):
        gallery = self.store.gallery(self.showroom)
        valid_ids = {staff_id for staff_id, _ in gallery}
        active = {t.id for t in tracks}
        self.matches = {key: value for key, value in self.matches.items()
                        if key in active and value[0] in valid_ids and now-value[2] <= 1}
        rows = detector.last_face_rows
        if rows is None or not gallery:
            return
        height, width = detector.last_face_image.shape[:2]
        candidates = {}
        for row in rows:
            if min(row[2:4]) < 48:
                continue
            x, y = (row[0]+row[2]/2)/width, (row[1]+row[3]/2)/height
            # Ambiguous overlapping person boxes never establish staff identity.
            owners = [t for t in tracks if t.observed and t.box[0] <= x <= t.box[2]
                      and t.box[1] <= y <= t.box[1]+.65*(t.box[3]-t.box[1])]
            if len(owners) != 1:
                for owner in owners:
                    self.matches.pop(owner.id, None)
                continue
            candidates.setdefault(owners[0].id, []).append(row)
        for track_id, face_rows in candidates.items():
            if len(face_rows) != 1:
                self.matches.pop(track_id, None)
                continue
            feature = self.recognizer.feature(detector.last_face_image, face_rows[0])
            ranked = sorted([(float(np.max(vectors @ feature)), staff_id) for staff_id, vectors in gallery], reverse=True)
            score, staff_id = ranked[0]
            # Conservative starting threshold; must be calibrated on site footage.
            if score < .5 or (len(ranked)>1 and score-ranked[1][0] < .08):
                self.matches.pop(track_id, None)
                continue
            previous = self.matches.get(track_id)
            hits = previous[1]+1 if previous and previous[0]==staff_id and now-previous[2] < .8 else 1
            self.matches[track_id] = (staff_id, hits, now)

    def is_staff(self, track_id, now):
        match = self.matches.get(track_id)
        return bool(match and match[1] >= 2 and now-match[2] <= 1)
