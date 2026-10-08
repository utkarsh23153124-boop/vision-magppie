import unittest

from vision.counting import LineCounter, Track, Tracker


def person(x, y=0.7):
    return ((x - 0.05, y - 0.25, x + 0.05, y), 0.9)


class CountingTests(unittest.TestCase):
    def count(self, positions, **kwargs):
        tracker = Tracker()
        counter = LineCounter(axis="vertical", **kwargs)
        events = []
        for index, x in enumerate(positions):
            timestamp = index / 10
            events.extend(counter.update(tracker.update([person(x)], timestamp), timestamp))
        return counter, events

    def test_entry_once_while_staying_inside(self):
        counter, events = self.count([.3, .32, .42, .49, .56, .62, .64, .63, .62])
        self.assertEqual((counter.entries, counter.exits), (1, 0))
        self.assertEqual(len(events), 1)

    def test_return_counts_exit_and_reentry_as_physical_events(self):
        counter, _ = self.count([.3, .32, .42, .55, .62, .56, .44, .36, .4, .55, .62])
        self.assertEqual((counter.entries, counter.exits), (2, 1))

    def test_reverse_direction(self):
        counter, events = self.count([.3, .32, .43, .55, .62], in_positive=False)
        self.assertEqual((counter.entries, counter.exits), (0, 1))
        self.assertEqual(events[0]["direction"], "OUT")

    def test_line_jitter_does_not_count(self):
        counter, _ = self.count([.4, .41, .49, .51, .495, .505, .48, .42])
        self.assertEqual(counter.entries + counter.exits, 0)

    def test_single_frame_on_other_side_not_enough(self):
        counter, _ = self.count([.4, .41, .54, .43, .42])
        self.assertEqual(counter.entries + counter.exits, 0)

    def test_first_appearance_inside_does_not_count(self):
        counter, _ = self.count([.6, .62, .64])
        self.assertEqual(counter.entries + counter.exits, 0)

    def test_first_appearance_on_line_does_not_count(self):
        counter, _ = self.count([.5, .51, .54, .56])
        self.assertEqual(counter.entries + counter.exits, 0)

    def test_long_gap_does_not_infer_a_crossing(self):
        tracker, counter = Tracker(), LineCounter(axis="vertical")
        for timestamp, x in [(0, .4), (.1, .41), (2, .55), (2.1, .6)]:
            counter.update(tracker.update([person(x)], timestamp), timestamp)
        self.assertEqual(counter.entries + counter.exits, 0)
        self.assertEqual(tracker.next_id, 3)

    def test_horizontal_uses_feet_not_face(self):
        tracker, counter = Tracker(), LineCounter(axis="horizontal")
        for index, y in enumerate([.3, .32, .44, .55, .62]):
            t = index / 10
            counter.update(tracker.update([person(.5, y)], t), t)
        self.assertEqual(counter.entries, 1)

    def test_two_people_can_cross_in_opposite_directions(self):
        tracker, counter = Tracker(), LineCounter(axis="vertical")
        for index, x in enumerate([.3, .32, .42, .56, .64]):
            t = index / 10
            tracks = tracker.update([person(x, .35), person(1 - x, .85)], t)
            counter.update(tracks, t)
        self.assertEqual((counter.entries, counter.exits), (1, 1))

    def test_unobserved_track_cannot_count(self):
        counter = LineCounter(axis="vertical")
        for t in [0, .1]:
            counter.update([Track(1, person(.3)[0], t, .9, hits=3)], t)
        for t in [.2, .3]:
            counter.update([Track(1, person(.7)[0], t, .9, hits=3, observed=False)], t)
        self.assertEqual(counter.entries, 0)

    def test_stale_tracks_are_removed(self):
        tracker, counter = Tracker(), LineCounter()
        counter.update(tracker.update([person(.3)], 0), 0)
        counter.update(tracker.update([], 2), 2)
        self.assertEqual(tracker.tracks, {})
        self.assertEqual(counter.states, {})

    def test_invalid_line_settings(self):
        with self.assertRaises(ValueError):
            LineCounter(position=2)
        with self.assertRaises(ValueError):
            LineCounter(axis="diagonal")


if __name__ == "__main__":
    unittest.main()
