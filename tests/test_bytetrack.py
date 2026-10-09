import unittest
from vision.bytetrack import ByteTracker, iou


class TestByteTracker(unittest.TestCase):
    def test_iou_calculation(self):
        a = (0.1, 0.1, 0.5, 0.5)
        b = (0.1, 0.1, 0.5, 0.5)
        self.assertAlmostEqual(iou(a, b), 1.0)

        c = (0.6, 0.6, 0.9, 0.9)
        self.assertAlmostEqual(iou(a, c), 0.0)

    def test_single_track_lifecycle_and_id_persistence(self):
        tracker = ByteTracker(max_age=1.0)
        # Frame 1: detect person
        dets1 = [((0.2, 0.2, 0.4, 0.6), 0.9)]
        tracks1 = tracker.update(dets1, timestamp=0.0)
        self.assertEqual(len(tracks1), 1)
        tid = tracks1[0].id
        self.assertEqual(tracks1[0].hits, 1)
        self.assertTrue(tracks1[0].observed)

        # Frame 2: person slightly moved
        dets2 = [((0.21, 0.21, 0.41, 0.61), 0.88)]
        tracks2 = tracker.update(dets2, timestamp=0.1)
        self.assertEqual(len(tracks2), 1)
        self.assertEqual(tracks2[0].id, tid)
        self.assertEqual(tracks2[0].hits, 2)
        self.assertTrue(tracks2[0].observed)

    def test_two_stage_association_with_low_confidence(self):
        tracker = ByteTracker(max_age=1.0, high_threshold=0.6, low_threshold=0.1)
        # Frame 1: high confidence detection initializes track
        tracker.update([((0.3, 0.3, 0.5, 0.7), 0.9)], timestamp=0.0)
        self.assertEqual(len(tracker.tracks), 1)

        # Frame 2: person partially occluded -> low confidence (0.4)
        tracks2 = tracker.update([((0.31, 0.31, 0.51, 0.71), 0.4)], timestamp=0.1)
        self.assertEqual(len(tracks2), 1)
        self.assertEqual(tracks2[0].hits, 2)
        self.assertEqual(tracks2[0].id, 1)
        self.assertTrue(tracks2[0].observed)

    def test_stale_tracks_removed(self):
        tracker = ByteTracker(max_age=0.5)
        tracker.update([((0.2, 0.2, 0.4, 0.6), 0.85)], timestamp=0.0)
        self.assertEqual(len(tracker.tracks), 1)

        # Skip time beyond max_age
        tracks = tracker.update([], timestamp=0.6)
        self.assertEqual(len(tracks), 0)


if __name__ == "__main__":
    unittest.main()
