import csv
import json
from pathlib import Path
import tempfile
import threading
import unittest

import cv2
import numpy as np

from vision.models import model_path, verified, MODELS
from vision.pipeline import Config, Journal, run, source_info


class FakeDetectors:
    def __init__(self):
        self.index = 0
        self.xs = [.3, .32, .42, .55, .62, .56, .44, .36]

    def people(self, frame):
        x = self.xs[self.index % len(self.xs)]
        self.index += 1
        return [((x - .05, .3, x + .05, .7), .9)]

    def faces(self, frame):
        return [((.1, .1, .2, .2), .9)]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.video = self.folder / "test.avi"
        writer = cv2.VideoWriter(str(self.video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (320, 240))
        self.assertTrue(writer.isOpened())
        for _ in range(8):
            writer.write(np.zeros((240, 320, 3), dtype=np.uint8))
        writer.release()

    def test_decode_count_and_export(self):
        result = run(Config(str(self.video), axis="vertical", output=self.folder / "results"), detectors=FakeDetectors())
        self.assertEqual((result["entries"], result["exits"]), (1, 1))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["frames"], 8)
        folder = Path(result["output_folder"])
        with (folder / "events.csv").open(newline="") as stream:
            events = list(csv.DictReader(stream))
        self.assertEqual([event["direction"] for event in events], ["IN", "OUT"])
        self.assertEqual(len({event["event_id"] for event in events}), 2)
        summary = json.loads((folder / "summary.json").read_text())
        self.assertEqual(summary["net_flow"], 0)
        self.assertEqual(summary["peak_faces"], 1)
        self.assertNotIn(str(self.video), json.dumps(summary))

    def test_browser_metadata_without_annotating_pixels(self):
        seen = []

        def callback(frame, stats, events):
            self.assertEqual(int(frame.max()), 0)
            self.assertTrue(stats["face_boxes"])
            self.assertTrue(stats["people_boxes"])
            self.assertGreaterEqual(stats["inference_ms"], 0)
            seen.append(stats)

        result = run(Config(str(self.video), axis="vertical", output=self.folder / "browser"),
                     callback=callback, detectors=FakeDetectors(), annotate_frames=False)
        self.assertEqual((result["entries"], result["exits"]), (1, 1))
        self.assertEqual(len(seen), 8)
        summary = json.loads((Path(result["output_folder"]) / "summary.json").read_text())
        self.assertNotIn("face_boxes", summary)

    def test_stop_flushes_a_session(self):
        stop = threading.Event()

        def callback(frame, stats, events):
            if stats["frames"] == 5:
                stop.set()

        result = run(Config(str(self.video), axis="vertical", output=self.folder / "results"), callback, stop, FakeDetectors())
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["entries"], 1)
        self.assertEqual(result["frames"], 5)

    def test_registered_crossings_excluded_without_saving_names(self):
        class Identity:
            def update(self,tracks,detector,faces,now):
                return [{'name':'PrivateFriendName','box':[.1,.1,.2,.2]}],{t.id for t in tracks}
        result=run(Config(str(self.video),axis='vertical',output=self.folder/'demo'),
                   detectors=FakeDetectors(),identity=Identity())
        self.assertEqual(result['entries'],0)
        self.assertEqual(result['exits'],0)
        self.assertEqual(result['staff_excluded'],2)
        folder=Path(result['output_folder'])
        with (folder/'events.csv').open(newline='') as file:
            events=list(csv.DictReader(file))
        self.assertTrue(all(e['category']=='staff' for e in events))
        self.assertNotIn('PrivateFriendName',(folder/'summary.json').read_text())
        self.assertNotIn('PrivateFriendName',(folder/'events.csv').read_text())

    def test_frame_limit_and_session_isolation(self):
        config = Config(str(self.video), output=self.folder / "results", max_frames=2)
        first = run(config, detectors=FakeDetectors())
        second = run(config, detectors=FakeDetectors())
        self.assertEqual(first["status"], "frame_limit")
        self.assertEqual(first["frames"], 2)
        self.assertNotEqual(first["output_folder"], second["output_folder"])

    def test_failed_detector_finalizes_error_summary(self):
        class Broken(FakeDetectors):
            def people(self, frame):
                raise RuntimeError("test failure")
        with self.assertRaises(RuntimeError):
            run(Config(str(self.video), output=self.folder / "results"), detectors=Broken())
        summaries = list((self.folder / "results").glob("*/summary.json"))
        self.assertEqual(json.loads(summaries[0].read_text())["status"], "error")

    def test_url_credentials_are_not_saved(self):
        config = Config("rtsp://user:secret@camera.local/feed", output=self.folder)
        journal = Journal(self.folder, config, "stream")
        journal.summary({"entries": 0})
        journal.close()
        text = (journal.folder / "summary.json").read_text()
        self.assertNotIn("secret", text)
        self.assertNotIn("camera.local", text)

    def test_source_validation(self):
        self.assertEqual(source_info("0"), ("webcam", 0))
        self.assertEqual(source_info(str(self.video))[0], "file")
        with self.assertRaises(ValueError):
            source_info("missing.mp4")
        with self.assertRaises(ValueError):
            source_info("ftp://example.com/video")
        with self.assertRaises(ValueError):
            Config("").validate()

    def test_checksum_rejects_tampered_model(self):
        path = self.folder / "bad.onnx"
        path.write_bytes(b"not a model")
        self.assertFalse(verified(path, MODELS["face"][1]))


if __name__ == "__main__":
    unittest.main()
