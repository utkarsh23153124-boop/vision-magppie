"""Stream health and telemetry tracker per camera worker."""
import threading
import time


class HealthMonitor:
    def __init__(self, camera_id):
        self.camera_id = camera_id
        self.lock = threading.Lock()
        self.frames_received = 0
        self.frames_dropped_stale = 0
        self.frames_processed = 0
        self.reconnect_count = 0
        self.last_good_frame_at = 0.0
        self.longest_gap_seconds = 0.0
        self._last_processed_mono = 0.0

    def record_received(self):
        with self.lock:
            self.frames_received += 1

    def record_stale_drop(self):
        with self.lock:
            self.frames_dropped_stale += 1

    def record_processed(self):
        now = time.monotonic()
        with self.lock:
            self.frames_processed += 1
            if self._last_processed_mono > 0:
                gap = now - self._last_processed_mono
                if gap > self.longest_gap_seconds:
                    self.longest_gap_seconds = round(gap, 2)
            self._last_processed_mono = now
            self.last_good_frame_at = now

    def record_reconnect(self):
        with self.lock:
            self.reconnect_count += 1

    def snapshot(self) -> dict:
        now = time.monotonic()
        with self.lock:
            age = round(now - self.last_good_frame_at, 1) if self.last_good_frame_at > 0 else None
            is_healthy = (self.last_good_frame_at > 0 and (now - self.last_good_frame_at) <= 30.0)
            drop_rate = (self.frames_dropped_stale / max(1, self.frames_received))
            return {
                "camera_id": self.camera_id,
                "frames_received": self.frames_received,
                "frames_dropped_stale": self.frames_dropped_stale,
                "frames_processed": self.frames_processed,
                "reconnect_count": self.reconnect_count,
                "drop_rate_pct": round(drop_rate * 100, 1),
                "seconds_since_last_frame": age,
                "longest_gap_seconds": self.longest_gap_seconds,
                "is_healthy": is_healthy,
            }
