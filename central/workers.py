"""Independent camera workers with bounded latest-frame capture and reconnection."""
from datetime import datetime, timezone
import os
import queue
import threading
import time
import uuid

import cv2

import os
import queue
import threading
import time
import uuid

import cv2

from vision.counting import Tracker, LineCounter, ZoneCounter
from vision.bytetrack import ByteTracker
from vision.detectors import Detectors, YoloDetectors
from vision.pipeline import open_capture, annotate
from central.staff import StaffMatcher
from central.health import HealthMonitor
from vision.uniform import UniformMatcher


# Visitors: minimum seconds between logging the same direction for the same
# track_id. Prevents double-counting when someone lingers near the counting
# line or the tracker momentarily loses-then-re-acquires the same person.
VISITOR_DIRECTION_COOLDOWN = 60


class VisitorCooldown:
    """In-memory gate: drop a (track_id, direction) crossing if the same pair
    was already logged within VISITOR_DIRECTION_COOLDOWN seconds."""

    def __init__(self, window=VISITOR_DIRECTION_COOLDOWN):
        self.window = window
        # {(track_id, direction): last_logged_monotonic}
        self._last: dict = {}

    def allow(self, track_id: int, direction: str, now: float) -> bool:
        key = (track_id, direction)
        last = self._last.get(key)
        if last is not None and now - last < self.window:
            return False
        self._last[key] = now
        return True

    def reset(self):
        self._last.clear()


class LatestFrames:
    def __init__(self, source, stop, state, opener=open_capture, health=None):
        self.source, self.stop, self.state, self.opener, self.health = source, stop, state, opener, health
        self.queue = queue.Queue(maxsize=1)
        self.thread = threading.Thread(target=self.read, daemon=True)

    def put(self, item):
        try:
            self.queue.get_nowait()
        except queue.Empty:
            pass
        try:
            self.queue.put_nowait(item)
        except queue.Full:
            pass

    def read(self):
        generation, backoff = 0, 1
        while not self.stop.is_set():
            capture = None
            try:
                self.state('connecting')
                if str(self.source).strip().isdigit():
                    kind, src = 'webcam', int(self.source)
                elif os.path.isfile(str(self.source)):
                    kind, src = 'file', str(self.source)
                else:
                    kind, src = 'stream', self.source
                capture = self.opener(kind, src)
                generation += 1
                connected = False
                while not self.stop.is_set():
                    ok, frame = capture.read()
                    if not ok:
                        raise RuntimeError('Input lost')
                    if not connected:
                        self.state('connected')
                        connected = True
                        backoff = 1
                        if self.health:
                            self.health.record_reconnect()
                    self.put((generation, time.monotonic(), datetime.now(timezone.utc).isoformat(), frame))
            except Exception:
                if not self.stop.is_set():
                    self.state('reconnecting')
            finally:
                if capture is not None:
                    capture.release()
            if self.stop.wait(backoff):
                break
            backoff = min(backoff * 2, 30)


class CameraWorker:
    def __init__(self, config, source, store, staff_store, uniform_store=None):
        self.config, self.source, self.store = config, source, store
        self.staff_store = staff_store
        self.uniform_store = uniform_store
        self.health = HealthMonitor(config['id'])
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.info = {'state': 'starting', 'frames': 0, 'ai_fps': 0, 'faces_now': 0}
        self.last_result = 0
        self.preview = None
        self.preview_at = 0
        self.uniform_matcher = UniformMatcher()
        self.reload_uniforms()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def reload_uniforms(self):
        if self.uniform_store and self.config.get('showroom'):
            profiles = self.uniform_store.gallery(self.config['showroom'])
            self.uniform_matcher.profiles = dict(profiles)

    def state(self, value):
        with self.lock:
            changed = self.info['state'] != value
            self.info['state'] = value
        if changed:
            self.store.log(self.config['id'], value)

    def snapshot(self):
        with self.lock:
            return {
                **self.info,
                'result_age_seconds': round(time.monotonic()-self.last_result, 1) if self.last_result else None,
                'worker_alive': self.thread.is_alive(),
                'health': self.health.snapshot()
            }

    def run(self):
        reader = None
        try:
            # Try YoloDetectors first; fallback to Detectors if models missing
            try:
                detectors = YoloDetectors()
            except Exception:
                detectors = Detectors()

            matcher = StaffMatcher(self.staff_store, self.config['showroom'], uniform_matcher=self.uniform_matcher)
            visitor_cooldown = VisitorCooldown()
            reader = LatestFrames(self.source, self.stop, self.state, health=self.health)
            reader.thread.start()
            generation, previous_time = None, None
            tracker, counter, run_id = None, None, None
            while not self.stop.is_set():
                try:
                    current, captured, observed_at, frame = reader.queue.get(timeout=.25)
                except queue.Empty:
                    continue

                self.health.record_received()

                if time.monotonic() - captured > 2.5:
                    self.health.record_stale_drop()
                    continue

                if current != generation or previous_time is None or captured - previous_time > 4.0:
                    tracker = ByteTracker()
                    if self.config.get('zone_mode'):
                        counter = ZoneCounter(self.config['axis'], float(self.config.get('position', 0.5)), in_positive=bool(self.config['in_positive']))
                    else:
                        counter = LineCounter(self.config['axis'], float(self.config.get('position', 0.5)), bool(self.config['in_positive']))
                    run_id = uuid.uuid4().hex
                    generation = current
                    matcher.matches.clear()
                    matcher.track_staff.clear()
                    visitor_cooldown.reset()
                previous_time = captured
                if frame.shape[1] > 960:
                    frame = cv2.resize(frame, (960, round(frame.shape[0]*960/frame.shape[1])))
                started = time.monotonic()
                people, faces = detectors.people(frame), detectors.faces(frame)
                tracks = tracker.update(people, captured)
                matcher.update(tracks, detectors, captured, frame=frame)
                events = counter.update(tracks, captured)
                for event in events:
                    if matcher.freq_suppressor:
                        matcher.freq_suppressor.record_crossing(event['track_id'], captured)
                    is_staff = matcher.is_staff(event['track_id'], captured)
                    event['category'] = 'staff' if is_staff else 'visitor'
                    # Attach the resolved staff_id so the DB can enforce the
                    # per-identity uniqueness window.
                    if is_staff:
                        event['staff_id'] = matcher.get_staff_id(event['track_id'])
                    else:
                        # Visitor deduplication: same track crossing same
                        # direction within VISITOR_DIRECTION_COOLDOWN is a
                        # phantom re-trigger — drop it.
                        if not visitor_cooldown.allow(event['track_id'], event['direction'], captured):
                            event['_drop'] = True
                events = [e for e in events if not e.get('_drop')]
                self.store.record(self.config['id'], run_id, events, observed_at)
                self.health.record_processed()
                elapsed = time.monotonic() - started
                if time.monotonic()-self.preview_at > 1:
                    staff_tracks = {t.id: matcher.get_staff_id(t.id) for t in tracks if matcher.is_staff(t.id, captured)}
                    rendered = annotate(frame, tracks, faces, counter, {'processing_fps':1/max(elapsed,.001)}, staff_tracks=staff_tracks)
                    ok, encoded = cv2.imencode('.jpg',rendered,[cv2.IMWRITE_JPEG_QUALITY,65])
                    if ok:
                        with self.lock:
                            self.preview = encoded.tobytes()
                            self.preview_at = time.monotonic()
                with self.lock:
                    self.last_result = time.monotonic()
                    self.info.update(frames=self.info['frames']+1, ai_fps=round(1/max(elapsed,.001),1),
                                     faces_now=len(faces), people_now=len(people),
                                     inference_ms=round(elapsed*1000),
                                     received_to_result_ms=round((self.last_result-captured)*1000),
                                     last_observed_at=observed_at)
        except Exception:
            self.state('error: check models, stream configuration or database')
        finally:
            self.stop.set()
            if reader:
                reader.thread.join(timeout=14)
            if not self.info['state'].startswith('error'):
                self.state('stopped')


class Manager:
    def __init__(self, store, staff_store, limit=4, uniform_store=None):
        self.store, self.limit = store, limit
        self.staff_store = staff_store
        self.uniform_store = uniform_store
        self.workers = {}
        self.lock = threading.Lock()

    def start(self, camera_id):
        with self.lock:
            old = self.workers.get(camera_id)
            if old and old.thread.is_alive():
                if old.stop.is_set():
                    raise ValueError('Camera is stopping. Retry shortly.')
                return
            if sum(w.thread.is_alive() for w in self.workers.values()) >= self.limit:
                raise ValueError('Server camera limit reached. Stop a camera or resize the server.')
            config = self.store.camera(camera_id)
            ref = config['source_ref']
            # Allow direct stream URL, webcam index, or file path; fallback to env variable
            source = ref if (ref.lower().startswith(('rtsp://', 'rtsps://', 'http://', 'https://')) or ref.isdigit() or os.path.isfile(ref)) else os.environ.get(ref, '')
            is_stream = source.lower().startswith(('rtsp://', 'rtsps://', 'http://', 'https://'))
            is_webcam = source.strip().isdigit()
            is_file = os.path.isfile(source)
            if not (is_stream or is_webcam or is_file):
                raise ValueError('Camera stream source is invalid or missing. Enter a direct RTSP/HTTP URL, webcam index (e.g. 0), local file path, or configured env secret name.')
            worker = CameraWorker(config, source, self.store, self.staff_store, self.uniform_store)
            self.store.set_enabled(camera_id, True)
            self.workers[camera_id] = worker
            worker.thread.start()

    def reload_uniforms(self, showroom=None):
        with self.lock:
            for worker in self.workers.values():
                if showroom is None or worker.config.get('showroom') == showroom:
                    worker.reload_uniforms()

    def stop(self, camera_id):
        with self.lock:
            self.store.set_enabled(camera_id, False)
            if camera_id in self.workers:
                self.workers[camera_id].stop.set()

    def delete(self, camera_id):
        with self.lock:
            if camera_id in self.workers:
                worker = self.workers.pop(camera_id)
                worker.stop.set()
            self.store.delete_camera(camera_id)

    def snapshot(self):
        with self.lock:
            return {key: worker.snapshot() for key, worker in self.workers.items()}

    def preview(self, camera_id):
        with self.lock:
            worker = self.workers.get(camera_id)
            if worker:
                with worker.lock:
                    if time.monotonic()-worker.preview_at < 5 and worker.thread.is_alive():
                        return worker.preview
        return None

    def configure(self, camera_id, data):
        with self.lock:
            worker = self.workers.get(camera_id)
            if worker and worker.thread.is_alive():
                raise ValueError('Stop the camera and wait for stopped status before changing its line.')
            self.store.set_line(camera_id,data.get('axis'),float(data.get('position',.5)),data.get('in_positive'))
            if 'zone_mode' in data:
                self.store.set_zone_mode(camera_id, data['zone_mode'])

    def restore(self):
        for camera in self.store.cameras():
            if camera['enabled']:
                try:
                    self.start(camera['id'])
                except ValueError:
                    self.store.log(camera['id'], 'restart blocked: check secret or capacity')

    def close(self):
        for worker in self.workers.values():
            worker.stop.set()
        for worker in self.workers.values():
            worker.thread.join(timeout=16)
