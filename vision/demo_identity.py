"""Local, opt-in demo gallery. Original photos remain in the user-owned folder.

Embeddings and names are kept in memory only, never written to crossing logs.
"""
from pathlib import Path

import cv2
import numpy as np

from central.staff import Recognizer
from vision.counting import Tracker
from vision.detectors import Detectors


def load_gallery(root, consent, detector=None, recognizer=None):
    if consent is not True:
        raise ValueError('Confirm that your friends agreed to this recognition demo.')
    root = Path(root).resolve()
    folders = [p for p in sorted(root.iterdir()) if p.is_dir() and not p.name.startswith(('.', '_'))]
    detector = detector or Detectors()
    recognizer = recognizer or Recognizer()
    result, errors = {}, []
    for folder in folders:
        if folder.is_symlink() or folder.resolve().parent != root:
            errors.append(f'{folder.name}: linked folders are not supported.')
            continue
        photos = [p for p in sorted(folder.iterdir()) if p.suffix.lower() in ('.jpg','.jpeg','.png','.webp')]
        if not photos:
            continue
        if len(photos)>5 or len(folder.name)>64:
            errors.append(f'{folder.name}: use 1–5 photos and a name under 65 characters.')
            continue
        vectors = []
        for photo in photos:
            try:
                if photo.is_symlink() or photo.resolve().parent != folder.resolve() or photo.stat().st_size>5_000_000:
                    raise ValueError('Use a regular image smaller than 5 MB.')
                image = cv2.imdecode(np.frombuffer(photo.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
                if image is None:
                    raise ValueError('Cannot decode image. Use JPEG, PNG or WebP.')
                vectors.append(recognizer.enroll(image,detector))
            except (ValueError, OSError, cv2.error) as error:
                errors.append(f'{folder.name}/{photo.name}: {error}')
        if len(vectors)==len(photos):
            result[folder.name] = np.array(vectors,dtype=np.float32)
    if errors:
        raise ValueError('\n'.join(errors))
    if not result:
        raise ValueError('No photos found. Put portraits in demo_photos/Name/ and import again.')
    return result


class DemoIdentity:
    def __init__(self, gallery, recognizer=None):
        self.gallery = gallery
        self.recognizer = recognizer or Recognizer()
        self.faces = Tracker()
        self.votes = {}

    def update(self, tracks, detector, faces, now):
        face_tracks = self.faces.update(faces,now)
        active = {t.id for t in face_tracks}
        self.votes = {key:value for key,value in self.votes.items() if key in active}
        rows = detector.last_face_rows
        labels, owners = [], {}
        for index,(box,score) in enumerate(faces):
            label, status = 'Unknown','unknown'
            matches = [t for t in face_tracks if t.observed and tuple(t.box)==tuple(box)]
            if len(matches)==1 and rows is not None and min(rows[index][2:4])>=48:
                face_id = matches[0].id
                vector = self.recognizer.feature(detector.last_face_image,rows[index])
                ranked = sorted([(float(np.max(samples@vector)),name) for name,samples in self.gallery.items()],reverse=True)
                if ranked and ranked[0][0]>=.5 and (len(ranked)==1 or ranked[0][0]-ranked[1][0]>=.08):
                    name=ranked[0][1]
                    previous=self.votes.get(face_id)
                    hits=previous[1]+1 if previous and previous[0]==name and now-previous[2]<.8 else 1
                    self.votes[face_id]=(name,hits,now)
                    if hits>=2:
                        label,status=name,'registered'
                    else:
                        label,status='Checking…','checking'
                else:
                    self.votes.pop(face_id,None)
            else:
                label,status='Move closer / face camera','unclear'
            item={'box':list(box),'name':label,'status':status}
            labels.append(item)
            x,y=(box[0]+box[2])/2,(box[1]+box[3])/2
            person_tracks=[t for t in tracks if t.observed and t.box[0]<=x<=t.box[2]
                           and t.box[1]<=y<=t.box[1]+.65*(t.box[3]-t.box[1])]
            if len(person_tracks)==1:
                owners.setdefault(person_tracks[0].id,[]).append(item)
        # Only a currently confirmed face with an unambiguous one-to-one link excludes a crossing.
        staff_ids={key for key,items in owners.items() if len(items)==1 and items[0]['status']=='registered'}
        return labels,staff_ids
