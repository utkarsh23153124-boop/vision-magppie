"""Shared processing engine for the desktop app and headless video evaluation."""
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import threading
import time
import uuid

import cv2

from .counting import LineCounter, Tracker
from .detectors import Detectors
from .models import ROOT


@dataclass(frozen=True)
class Config:
    source: str
    axis: str = "horizontal"
    position: float = 0.5
    in_positive: bool = True
    person_threshold: float = 0.40
    face_threshold: float = 0.80
    output: Path = ROOT / "output"
    max_frames: int = 0
    width: int = 960

    def validate(self):
        if not self.source.strip():
            raise ValueError("Choose a video file, webcam index, or camera stream.")
        LineCounter(self.axis, self.position, self.in_positive)
        if not 0.1 <= self.person_threshold <= 0.95 or not 0.1 <= self.face_threshold <= 0.99:
            raise ValueError("Detection thresholds must be between 0.1 and 0.95 (face: 0.99).")
        if self.width < 320 or self.width > 1920 or self.max_frames < 0:
            raise ValueError("Width must be 320–1920; max frames must be nonnegative.")


def source_info(source):
    if "://" in source:
        if not source.lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
            raise ValueError("Use an RTSP/HTTP stream, a video file, or a webcam number.")
        return "stream", source
    if Path(source).is_file():
        return "file", source
    if source.isdecimal():
        return "webcam", int(source)
    raise ValueError("Video file was not found. Use Browse or check the local path.")


def open_capture(kind, source):
    import os
    os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"
    if hasattr(cv2, "setLogLevel"):
        cv2.setLogLevel(0)
    if kind == "stream":
        capture = cv2.VideoCapture(source, cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 6000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, 4000,
        ])
    else:
        capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        capture.release()
        raise RuntimeError("Could not open input. Check the file, webcam permission, or camera connection.")
    return capture


class Journal:
    def __init__(self, folder, config, kind):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.session = f"{stamp}_{uuid.uuid4().hex[:8]}"
        self.folder = Path(folder) / self.session
        self.folder.mkdir(parents=True, exist_ok=False)
        self.file = (self.folder / "events.csv").open("w", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.file, fieldnames=[
            "event_id", "session_id", "processed_at_utc", "source_seconds", "track_id", "direction", "category"
        ])
        self.writer.writeheader()
        self.file.flush()
        self.meta = {"session_id": self.session, "source_kind": kind,
                     "axis": config.axis, "position": config.position,
                     "in_positive": config.in_positive,
                     "person_threshold": config.person_threshold,
                     "face_threshold": config.face_threshold,
                     "scope": "physical person crossings; no identity or group deduplication"}

    def write(self, events):
        for event in events:
            self.writer.writerow({**event, "event_id": uuid.uuid4().hex,
                                  "session_id": self.session,
                                  "processed_at_utc": datetime.now(timezone.utc).isoformat()})
        self.file.flush()

    def summary(self, stats):
        temp = self.folder / "summary.tmp"
        temp.write_text(json.dumps({**self.meta, **stats}, indent=2), encoding="utf-8")
        temp.replace(self.folder / "summary.json")

    def close(self):
        self.file.close()


def annotate(frame, tracks, faces, counter, stats, staff_tracks=None):
    h, w = frame.shape[:2]
    staff_tracks = staff_tracks or {}
    for track in tracks:
        if not track.observed:
            continue
        x1, y1, x2, y2 = (round(v * size) for v, size in zip(track.box, (w, h, w, h)))
        is_staff = track.id in staff_tracks
        color = (240, 180, 50) if is_staff else (105, 220, 100)
        label = "Staff" if is_staff else f"Person {track.id}"
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, label, (x1, max(18, y1 - 7)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
        # Centroid marker matching counting axis coordinate
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        cv2.circle(frame, (cx, cy), 5, color, -1)
    for box, _ in faces:
        x1, y1, x2, y2 = (round(v * size) for v, size in zip(box, (w, h, w, h)))
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 180, 75), 2)
    color = (50, 200, 255)
    if counter.axis == "horizontal":
        coordinate = round(h * counter.position)
        cv2.line(frame, (0, coordinate), (w - 1, coordinate), color, 2)
        for offset in (-counter.margin, counter.margin):
            y = round(h * (counter.position + offset))
            cv2.line(frame, (0, y), (w - 1, y), (110, 110, 110), 1)
        sign = 1 if counter.in_positive else -1
        cv2.arrowedLine(frame, (w - 40, coordinate - sign * 28), (w - 40, coordinate + sign * 28), color, 3)
    else:
        coordinate = round(w * counter.position)
        cv2.line(frame, (coordinate, 0), (coordinate, h - 1), color, 2)
        for offset in (-counter.margin, counter.margin):
            x = round(w * (counter.position + offset))
            cv2.line(frame, (x, 0), (x, h - 1), (110, 110, 110), 1)
        sign = 1 if counter.in_positive else -1
        cv2.arrowedLine(frame, (coordinate - sign * 28, h - 40), (coordinate + sign * 28, h - 40), color, 3)
    cv2.rectangle(frame, (0, 0), (w, 42), (24, 30, 37), -1)
    cv2.putText(frame, f"IN {counter.entries}   OUT {counter.exits}   Faces {len(faces)}   {stats['processing_fps']:.1f} FPS",
                (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (240, 240, 240), 2, cv2.LINE_AA)
    return frame


def run(config, callback=None, stop=None, detectors=None, capture_override=None, annotate_frames=True, identity=None):
    """Blocking worker. Callback receives current frame/stats/events; never uses Tk."""
    config.validate()
    stop = stop or threading.Event()
    kind, source = source_info(config.source)
    detectors = detectors or Detectors(config.person_threshold, config.face_threshold)
    capture = capture_override if capture_override is not None else open_capture(kind, source)
    journal = None
    start = time.monotonic()
    stats = {"entries": 0, "exits": 0, "net_flow": 0, "frames": 0,
             "faces_now": 0, "people_now": 0, "processing_fps": 0.0,
             "peak_faces": 0, "source_seconds": 0.0, "status": "running", "staff_excluded": 0}
    try:
        journal = Journal(config.output, config, kind)
        if identity:
            journal.meta['scope'] = 'demo physical crossings with confirmed registered faces excluded; not unique visitors'
        counter = LineCounter(config.axis, config.position, config.in_positive)
        tracker = Tracker()
        fps = capture.get(cv2.CAP_PROP_FPS)
        valid_fps = math.isfinite(fps) and fps > 0
        source_fps = fps if valid_fps else 30.0
        stats["source_fps_assumed"] = kind == "file" and not valid_fps
        reported_frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        expected_frames = int(reported_frames) if math.isfinite(reported_frames) and reported_frames > 0 else 0
        while not stop.is_set():
            ok, frame = capture.read()
            if not ok:
                if kind == "file" and stats["frames"] and (not expected_frames or stats["frames"] >= expected_frames - 1):
                    stats["status"] = "completed"
                else:
                    stats["status"] = "input_lost_or_decode_error"
                break
            timestamp = stats["frames"] / source_fps if kind == "file" else time.monotonic() - start
            if frame.shape[1] > config.width:
                frame = cv2.resize(frame, (config.width, round(frame.shape[0] * config.width / frame.shape[1])))
            inference_start = time.monotonic()
            people = detectors.people(frame)
            faces = detectors.faces(frame)
            stats["inference_ms"] = round((time.monotonic() - inference_start) * 1000, 1)
            tracks = tracker.update(people, timestamp)
            labels, staff_ids = identity.update(tracks, detectors, faces, timestamp) if identity else ([], set())
            stats["inference_ms"] = round((time.monotonic()-inference_start)*1000,1)
            events = counter.update(tracks, timestamp)
            for event in events:
                event['category'] = 'staff' if event['track_id'] in staff_ids else 'visitor'
                if event['category']=='staff':
                    stats['staff_excluded'] += 1
                else:
                    stats['entries' if event['direction']=='IN' else 'exits'] += 1
            journal.write(events)
            stats.update(net_flow=stats['entries'] - stats['exits'],
                         frames=stats["frames"] + 1, faces_now=len(faces), people_now=len(people),
                         peak_faces=max(stats["peak_faces"], len(faces)), source_seconds=round(timestamp, 3))
            stats["processing_fps"] = round(stats["frames"] / max(0.001, time.monotonic() - start), 2)
            if stats["frames"] == 1 or stats["frames"] % 30 == 0:
                journal.summary(stats)
            if callback:
                preview_stats = {**stats, "people_boxes": [list(t.box) for t in tracks if t.observed],
                                 "face_boxes": [list(box) for box, score in faces], "face_labels": labels}
                callback(annotate(frame, tracks, faces, counter, stats) if annotate_frames else frame,
                         preview_stats, events)
            if config.max_frames and stats["frames"] >= config.max_frames:
                stats["status"] = "frame_limit"
                break
        if stop.is_set():
            stats["status"] = "stopped"
    except BaseException:
        stats["status"] = "error"
        raise
    finally:
        capture.release()
        if journal:
            try:
                stats["elapsed_seconds"] = round(time.monotonic() - start, 3)
                journal.summary(stats)
            finally:
                journal.close()
    return {**stats, "output_folder": str(journal.folder)}
