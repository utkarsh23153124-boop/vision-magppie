"""Self-contained ByteTrack-style tracker using linear Kalman filtering and two-stage matching."""
from dataclasses import dataclass
from math import hypot
import numpy as np


def iou(a, b):
    inter_w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    inter_h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = inter_w * inter_h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0.0


class SimpleKalmanBox:
    """Kalman Filter for tracking bounding boxes in cx, cy, w, h space."""

    def __init__(self, box):
        # box: (x1, y1, x2, y2)
        cx = (box[0] + box[2]) / 2.0
        cy = (box[1] + box[3]) / 2.0
        w = max(1e-4, box[2] - box[0])
        h = max(1e-4, box[3] - box[1])

        # State vector: [cx, cy, w, h, vx, vy, vw, vh]
        self.x = np.array([cx, cy, w, h, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)

        # State transition matrix F (dt = 1)
        self.F = np.eye(8, dtype=np.float32)
        for i in range(4):
            self.F[i, i + 4] = 1.0

        # Measurement matrix H
        self.H = np.eye(4, 8, dtype=np.float32)

        # Covariance matrices
        self.P = np.eye(8, dtype=np.float32) * 10.0
        self.Q = np.eye(8, dtype=np.float32) * 0.01
        self.Q[4:, 4:] *= 0.1
        self.R = np.eye(4, dtype=np.float32) * 0.1

    def predict(self):
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.get_box()

    def update(self, box):
        cx = (box[0] + box[2]) / 2.0
        cy = (box[1] + box[3]) / 2.0
        w = max(1e-4, box[2] - box[0])
        h = max(1e-4, box[3] - box[1])
        z = np.array([cx, cy, w, h], dtype=np.float32)

        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(8, dtype=np.float32) - K @ self.H) @ self.P

    def get_box(self):
        cx, cy, w, h = self.x[:4]
        x1 = cx - w / 2.0
        y1 = cy - h / 2.0
        x2 = cx + w / 2.0
        y2 = cy + h / 2.0
        return (float(x1), float(y1), float(x2), float(y2))


@dataclass
class Track:
    id: int
    box: tuple
    last_seen: float
    score: float
    hits: int = 1
    observed: bool = True
    time_since_update: int = 0
    state: str = "tracked"  # "tracked", "lost", "removed"


class ByteTracker:
    """ByteTrack tracker with two-stage association matching.
    
    Compatible with vision.counting.Tracker public interface.
    """

    def __init__(self, max_age=2.0, high_threshold=0.45, low_threshold=0.10, match_thresh=0.25):
        self.max_age = max_age
        self.high_threshold = high_threshold
        self.low_threshold = low_threshold
        self.match_thresh = match_thresh
        self.tracks = {}  # id -> Track
        self.kalmans = {}  # id -> SimpleKalmanBox
        self.next_id = 1

    def update(self, detections, timestamp):
        # 1. Predict current locations of all active tracks
        for tid, track in list(self.tracks.items()):
            track.time_since_update += 1
            if tid in self.kalmans:
                predicted_box = self.kalmans[tid].predict()
                track.box = predicted_box
            track.observed = False

        # 2. Partition detections into high and low confidence
        high_dets = []
        low_dets = []
        for box, score in detections:
            if score >= self.high_threshold:
                high_dets.append((box, score))
            elif score >= self.low_threshold:
                low_dets.append((box, score))

        # 3. Stage 1: Match tracked tracks with high-confidence detections
        active_track_ids = [tid for tid, t in self.tracks.items() if t.state in ("tracked", "lost")]
        matched_tracks_1, unmatched_tracks_1, unmatched_high = self._match(active_track_ids, high_dets, self.match_thresh)

        # Update matched tracks from stage 1
        for tid, d_idx in matched_tracks_1:
            box, score = high_dets[d_idx]
            track = self.tracks[tid]
            track.box = box
            track.score = score
            track.last_seen = timestamp
            track.hits += 1
            track.observed = True
            track.time_since_update = 0
            track.state = "tracked"
            if tid in self.kalmans:
                self.kalmans[tid].update(box)

        # 4. Stage 2: Match remaining unmatched tracks with low-confidence detections
        matched_tracks_2, unmatched_tracks_2, _ = self._match(unmatched_tracks_1, low_dets, 0.15)

        for tid, d_idx in matched_tracks_2:
            box, score = low_dets[d_idx]
            track = self.tracks[tid]
            track.box = box
            track.score = score
            track.last_seen = timestamp
            track.hits += 1
            track.observed = True
            track.time_since_update = 0
            track.state = "tracked"
            if tid in self.kalmans:
                self.kalmans[tid].update(box)

        # Any track unmatched after stage 2 is marked lost
        for tid in unmatched_tracks_2:
            track = self.tracks[tid]
            track.state = "lost"

        # 5. Initialize new tracks from unmatched high-confidence detections
        for d_idx in unmatched_high:
            box, score = high_dets[d_idx]
            tid = self.next_id
            self.next_id += 1
            new_track = Track(
                id=tid,
                box=box,
                last_seen=timestamp,
                score=score,
                hits=1,
                observed=True,
                time_since_update=0,
                state="tracked",
            )
            self.tracks[tid] = new_track
            self.kalmans[tid] = SimpleKalmanBox(box)

        # 6. Remove old tracks that have exceeded max_age (in seconds) or too many frames
        for tid, track in list(self.tracks.items()):
            if (timestamp - track.last_seen) > self.max_age:
                del self.tracks[tid]
                self.kalmans.pop(tid, None)

        return list(self.tracks.values())

    def _match(self, track_ids, detections, threshold):
        if not track_ids or not detections:
            return [], list(track_ids), list(range(len(detections)))

        candidates = []
        for t_idx, tid in enumerate(track_ids):
            t_box = self.tracks[tid].box
            for d_idx, (d_box, _) in enumerate(detections):
                score = iou(t_box, d_box)
                if score >= threshold:
                    candidates.append((score, tid, d_idx))

        # Greedy match by highest IoU
        matched_tracks = []
        matched_tids = set()
        matched_d_indices = set()
        for score, tid, d_idx in sorted(candidates, key=lambda c: c[0], reverse=True):
            if tid in matched_tids or d_idx in matched_d_indices:
                continue
            matched_tracks.append((tid, d_idx))
            matched_tids.add(tid)
            matched_d_indices.add(d_idx)

        unmatched_tracks = [tid for tid in track_ids if tid not in matched_tids]
        unmatched_detections = [d_idx for d_idx in range(len(detections)) if d_idx not in matched_d_indices]
        return matched_tracks, unmatched_tracks, unmatched_detections
