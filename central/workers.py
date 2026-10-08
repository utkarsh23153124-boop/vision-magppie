"""Independent camera workers with bounded latest-frame capture and reconnection."""
from datetime import datetime, timezone
import os
import queue
import threading
import time
import uuid

import cv2

from vision.counting import Tracker, LineCounter
from vision.detectors import Detectors
from vision.pipeline import open_capture, annotate
from central.staff import StaffMatcher


class LatestFrames:
    def __init__(self, source, stop, state, opener=open_capture):
        self.source, self.stop, self.state, self.opener = source, stop, state, opener
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
                capture = self.opener('stream', self.source)
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
    def __init__(self, config, source, store, staff_store):
        self.config, self.source, self.store = config, source, store
        self.staff_store = staff_store
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.info = {'state': 'starting', 'frames': 0, 'ai_fps': 0, 'faces_now': 0}
        self.last_result = 0
        self.preview = None
        self.preview_at = 0
        self.thread = threading.Thread(target=self.run, daemon=True)

    def state(self, value):
        with self.lock:
            changed = self.info['state'] != value
            self.info['state'] = value
        if changed:
            self.store.log(self.config['id'], value)

    def snapshot(self):
        with self.lock:
            return {**self.info, 'result_age_seconds': round(time.monotonic()-self.last_result, 1)
                    if self.last_result else None, 'worker_alive': self.thread.is_alive()}

    def run(self):
        reader = None
        try:
            detectors = Detectors()
            matcher = StaffMatcher(self.staff_store, self.config['showroom'])
            reader = LatestFrames(self.source, self.stop, self.state)
            reader.thread.start()
            generation, previous_time = None, None
            tracker, counter, run_id = None, None, None
            while not self.stop.is_set():
                try:
                    current, captured, observed_at, frame = reader.queue.get(timeout=.25)
                except queue.Empty:
                    continue
                if time.monotonic() - captured > 1:
                    continue
                if current != generation or previous_time is None or captured - previous_time > .8:
                    tracker = Tracker()
                    counter = LineCounter(self.config['axis'], self.config['position'], bool(self.config['in_positive']))
                    run_id = uuid.uuid4().hex
                    generation = current
                    matcher.matches.clear()
                previous_time = captured
                if frame.shape[1] > 960:
                    frame = cv2.resize(frame, (960, round(frame.shape[0]*960/frame.shape[1])))
                started = time.monotonic()
                people, faces = detectors.people(frame), detectors.faces(frame)
                tracks = tracker.update(people, captured)
                matcher.update(tracks, detectors, captured)
                events = counter.update(tracks, captured)
                for event in events:
                    event['category'] = 'staff' if matcher.is_staff(event['track_id'], captured) else 'visitor'
                self.store.record(self.config['id'], run_id, events, observed_at)
                elapsed = time.monotonic() - started
                if time.monotonic()-self.preview_at > 1:
                    rendered = annotate(frame, tracks, faces, counter, {'processing_fps':1/max(elapsed,.001)})
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
    def __init__(self, store, staff_store, limit=4):
        self.store, self.limit = store, limit
        self.staff_store = staff_store
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
            source = os.environ.get(config['source_ref'], '')
            if not source.lower().startswith(('rtsp://', 'rtsps://', 'http://', 'https://')):
                raise ValueError('Camera secret is missing on the server or is not a stream URL.')
            worker = CameraWorker(config, source, self.store, self.staff_store)
            self.store.set_enabled(camera_id, True)
            self.workers[camera_id] = worker
            worker.thread.start()

    def stop(self, camera_id):
        with self.lock:
            self.store.set_enabled(camera_id, False)
            if camera_id in self.workers:
                self.workers[camera_id].stop.set()

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
