import unittest
import numpy as np

from vision.uniform import UniformMatcher, FrequencySuppressor


class TestUniformMatcher(unittest.TestCase):
    def test_uniform_registration_and_match(self):
        matcher = UniformMatcher(match_threshold=0.60)
        # Register a bright red uniform
        red_img = np.zeros((100, 100, 3), dtype=np.uint8)
        red_img[:, :] = (0, 0, 255)  # BGR Red
        matcher.register_uniform("red_team", [red_img])

        self.assertIn("red_team", matcher.profiles)

        # Test matching red person box
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        frame[50:150, 50:150] = (0, 0, 255)
        box = (0.25, 0.25, 0.75, 0.75)
        is_match, conf = matcher.is_uniform_match(frame, box)
        self.assertTrue(is_match)
        self.assertGreater(conf, 0.60)

        # Test non-matching blue person box
        frame_blue = np.zeros((200, 200, 3), dtype=np.uint8)
        frame_blue[50:150, 50:150] = (255, 0, 0)
        is_match_blue, conf_blue = matcher.is_uniform_match(frame_blue, box)
        self.assertFalse(is_match_blue)
        self.assertLess(conf_blue, 0.50)

    def test_frequency_suppressor(self):
        suppressor = FrequencySuppressor(window_seconds=10.0, threshold=3)
        self.assertFalse(suppressor.is_frequent(1, current_time=0.0))

        suppressor.record_crossing(1, timestamp=0.0)
        suppressor.record_crossing(1, timestamp=1.0)
        self.assertFalse(suppressor.is_frequent(1, current_time=2.0))

        suppressor.record_crossing(1, timestamp=2.0)
        self.assertTrue(suppressor.is_frequent(1, current_time=2.5))

        # After window_seconds passes, old crossings expire
        self.assertFalse(suppressor.is_frequent(1, current_time=15.0))


if __name__ == "__main__":
    unittest.main()
