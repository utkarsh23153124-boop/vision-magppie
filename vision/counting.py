"""Dependency-free short-term tracker and hysteresis line counter.

This baseline is for light doorway traffic, not persistent identity or crowded MOT.
All coordinates are normalized to the frame. Only observed tracks can count.
"""
from dataclasses import dataclass
from math import hypot


def centre(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0


@dataclass
class Track:
    id: int
    box: tuple
    last_seen: float
    score: float
    hits: int = 1
    observed: bool = True


class Tracker:
    def __init__(self, max_age=0.8, max_distance=0.16):
        self.max_age = max_age
        self.max_distance = max_distance
        self.tracks = {}
        self.next_id = 1

    def update(self, detections, timestamp):
        self.tracks = {key: track for key, track in self.tracks.items()
                       if timestamp - track.last_seen <= self.max_age}
        candidates = []
        for key, track in self.tracks.items():
            track.observed = False
            tx, ty = centre(track.box)
            for index, (box, _) in enumerate(detections):
                dx, dy = centre(box)
                distance = hypot(tx - dx, ty - dy)
                overlap = iou(track.box, box)
                if distance <= self.max_distance:
                    candidates.append((distance + 0.05 * (1 - overlap), key, index))
        assigned_tracks, assigned_detections = set(), set()
        for _, key, index in sorted(candidates):
            if key in assigned_tracks or index in assigned_detections:
                continue
            track = self.tracks[key]
            track.box, track.score = detections[index]
            track.last_seen = timestamp
            track.hits += 1
            track.observed = True
            assigned_tracks.add(key)
            assigned_detections.add(index)
        for index, (box, score) in enumerate(detections):
            if index not in assigned_detections:
                self.tracks[self.next_id] = Track(self.next_id, box, timestamp, score)
                self.next_id += 1
        return list(self.tracks.values())


@dataclass
class SideState:
    stable: int = 0
    candidate: int = 0
    observations: int = 0
    last_seen: float = 0


class LineCounter:
    def __init__(self, axis="horizontal", position=0.5, in_positive=True,
                 margin=0.025, stable_frames=2, max_gap=0.8):
        if axis not in ("horizontal", "vertical"):
            raise ValueError("Line axis must be horizontal or vertical.")
        if not 0.1 <= position <= 0.9:
            raise ValueError("Line position must be between 0.1 and 0.9.")
        self.axis, self.position, self.in_positive = axis, position, in_positive
        self.margin, self.stable_frames, self.max_gap = margin, stable_frames, max_gap
        self.states = {}
        self.entries = self.exits = 0

    def update(self, tracks, timestamp):
        active_ids = {track.id for track in tracks}
        self.states = {key: state for key, state in self.states.items() if key in active_ids}
        events = []
        for track in tracks:
            if not track.observed:
                continue
            state = self.states.setdefault(track.id, SideState(last_seen=timestamp))
            if timestamp - state.last_seen > self.max_gap:
                state = self.states[track.id] = SideState(last_seen=timestamp)
            state.last_seen = timestamp
            # Bottom centre follows ground contact for a full-body entrance view.
            coordinate = track.box[3] if self.axis == "horizontal" else centre(track.box)[0]
            delta = coordinate - self.position
            side = 1 if delta > self.margin else -1 if delta < -self.margin else 0
            if side == 0:
                state.candidate, state.observations = 0, 0
                continue
            if side == state.candidate:
                state.observations += 1
            else:
                state.candidate, state.observations = side, 1
            if state.observations < self.stable_frames or track.hits < self.stable_frames:
                continue
            if state.stable and state.stable != side:
                direction = "IN" if (side == 1) == self.in_positive else "OUT"
                self.entries += direction == "IN"
                self.exits += direction == "OUT"
                events.append({"track_id": track.id, "direction": direction,
                               "source_seconds": round(timestamp, 3)})
            state.stable = side
        return events
