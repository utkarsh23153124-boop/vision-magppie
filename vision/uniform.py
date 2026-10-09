"""Multi-signal staff filter components: uniform color histogram matching and crossing frequency suppression."""
from collections import defaultdict
import cv2
import numpy as np


class UniformMatcher:
    """Secondary staff filter matching upper-body clothing color histograms in HSV space."""

    def __init__(self, match_threshold=0.65):
        self.match_threshold = match_threshold
        self.profiles = {}  # label -> np.ndarray normalized histogram

    def register_uniform(self, label: str, sample_frames: list):
        """Register uniform profile using sample images of a person or uniform.
        
        Computes 3D HSV histogram of the upper 45% of the frame and averages them.
        """
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

        if hists:
            avg_hist = np.mean(hists, axis=0)
            cv2.normalize(avg_hist, avg_hist, alpha=1.0, norm_type=cv2.NORM_L2)
            self.profiles[label] = avg_hist

    def is_uniform_match(self, frame, box_normalized) -> tuple[bool, float]:
        """Check if upper torso of a detected person matches any registered uniform profile.
        
        box_normalized: (x1, y1, x2, y2) in [0, 1] range.
        Returns: (is_match: bool, best_similarity: float in [0, 1]).
        """
        if not self.profiles or frame is None or frame.size == 0:
            return False, 0.0

        h, w = frame.shape[:2]
        x1 = max(0, min(w - 1, int(box_normalized[0] * w)))
        y1 = max(0, min(h - 1, int(box_normalized[1] * h)))
        x2 = max(x1 + 1, min(w, int(box_normalized[2] * w)))
        y2 = max(y1 + 1, min(h, int(box_normalized[3] * h)))

        torso_y2 = y1 + max(1, int((y2 - y1) * 0.45))
        upper_crop = frame[y1:torso_y2, x1:x2]
        if upper_crop.size == 0 or upper_crop.shape[0] < 5 or upper_crop.shape[1] < 5:
            return False, 0.0

        hsv = cv2.cvtColor(upper_crop, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [32, 32, 32], [0, 180, 0, 256, 0, 256])
        cv2.normalize(hist, hist, alpha=1.0, norm_type=cv2.NORM_L2)

        best_similarity = 0.0
        for label, ref_hist in self.profiles.items():
            # Bhattacharyya distance in [0, 1] where 0 is perfect match
            dist = cv2.compareHist(hist, ref_hist, cv2.HISTCMP_BHATTACHARYYA)
            similarity = max(0.0, 1.0 - float(dist))
            if similarity > best_similarity:
                best_similarity = similarity

        is_match = best_similarity >= self.match_threshold
        return is_match, float(best_similarity)


class FrequencySuppressor:
    """Tertiary staff filter: tracks crossing frequency within a sliding time window."""

    def __init__(self, window_seconds=3600.0, threshold=8):
        self.window_seconds = window_seconds
        self.threshold = threshold
        self.crossings = defaultdict(list)  # track_id -> list of float timestamps

    def record_crossing(self, track_id: int, timestamp: float):
        self.crossings[track_id].append(timestamp)
        self.prune(timestamp)

    def is_frequent(self, track_id: int, current_time: float) -> bool:
        recent = [t for t in self.crossings.get(track_id, []) if (current_time - t) <= self.window_seconds]
        return len(recent) >= self.threshold

    def prune(self, current_time: float):
        for tid in list(self.crossings.keys()):
            valid = [t for t in self.crossings[tid] if (current_time - t) <= self.window_seconds]
            if valid:
                self.crossings[tid] = valid
            else:
                del self.crossings[tid]
