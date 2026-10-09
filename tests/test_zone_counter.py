import unittest
from vision.counting import ZoneCounter, Track


class TestZoneCounter(unittest.TestCase):
    def test_zone_counter_in_crossing(self):
        counter = ZoneCounter(axis="vertical", outer_position=0.40, inner_position=0.60,
                              in_positive=True, stable_frames=2)
        # Frame 1: Person on left side (x=0.30)
        t1 = Track(id=1, box=(0.25, 0.2, 0.35, 0.8), last_seen=0.0, score=0.9, hits=1, observed=True)
        events = counter.update([t1], timestamp=0.0)
        self.assertEqual(len(events), 0)

        # Frame 2: Person still on left side (x=0.32) -> confirms outside
        t2 = Track(id=1, box=(0.27, 0.2, 0.37, 0.8), last_seen=0.1, score=0.9, hits=2, observed=True)
        events = counter.update([t2], timestamp=0.1)
        self.assertEqual(len(events), 0)

        # Frame 3: Person in middle buffer zone (x=0.50) -> no crossing yet
        t3 = Track(id=1, box=(0.45, 0.2, 0.55, 0.8), last_seen=0.2, score=0.9, hits=3, observed=True)
        events = counter.update([t3], timestamp=0.2)
        self.assertEqual(len(events), 0)

        # Frame 4: Person moves to right side (x=0.70)
        t4 = Track(id=1, box=(0.65, 0.2, 0.75, 0.8), last_seen=0.3, score=0.9, hits=4, observed=True)
        events = counter.update([t4], timestamp=0.3)
        self.assertEqual(len(events), 0)

        # Frame 5: Person stays on right side (x=0.72) -> 2 stable frames -> confirmed IN crossing!
        t5 = Track(id=1, box=(0.67, 0.2, 0.77, 0.8), last_seen=0.4, score=0.9, hits=5, observed=True)
        events = counter.update([t5], timestamp=0.4)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["direction"], "IN")
        self.assertEqual(counter.entries, 1)
        self.assertEqual(counter.exits, 0)

    def test_oscillation_in_buffer_zone_does_not_count(self):
        counter = ZoneCounter(axis="vertical", outer_position=0.40, inner_position=0.60,
                              in_positive=True, stable_frames=2)
        # Person moves only within [0.42, 0.58]
        for i in range(10):
            x = 0.50 + (0.05 if i % 2 == 0 else -0.05)
            t = Track(id=2, box=(x - 0.05, 0.2, x + 0.05, 0.8), last_seen=float(i), score=0.9, hits=i + 1, observed=True)
            events = counter.update([t], timestamp=float(i))
            self.assertEqual(len(events), 0)

        self.assertEqual(counter.entries, 0)
        self.assertEqual(counter.exits, 0)


if __name__ == "__main__":
    unittest.main()
