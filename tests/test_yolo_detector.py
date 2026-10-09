import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from vision.detectors import YoloDetectors


class TestYoloDetectors(unittest.TestCase):
    @patch("vision.detectors.require_models")
    @patch("vision.detectors.model_path")
    @patch("cv2.FaceDetectorYN.create")
    @patch("onnxruntime.InferenceSession")
    def test_missing_model_raises_error(self, mock_session, mock_yn, mock_model_path, mock_require):
        mock_require.side_effect = RuntimeError("Model yolo_person missing")
        with self.assertRaises(RuntimeError):
            YoloDetectors()

    @patch("vision.detectors.require_models")
    @patch("vision.detectors.model_path")
    @patch("cv2.FaceDetectorYN.create")
    @patch("onnxruntime.InferenceSession")
    def test_yolo_detection_decoding(self, mock_session_cls, mock_yn, mock_model_path, mock_require):
        mock_model_path.return_value = "fake_path.onnx"
        mock_session = MagicMock()
        mock_input = MagicMock()
        mock_input.name = "images"
        mock_session.get_inputs.return_value = [mock_input]

        # Construct synthetic ONNX output: (1, 84, 8400)
        # One high confidence person at cx=320, cy=320, w=100, h=200
        raw_out = np.zeros((1, 84, 8400), dtype=np.float32)
        raw_out[0, 0, 0] = 320.0  # cx
        raw_out[0, 1, 0] = 320.0  # cy
        raw_out[0, 2, 0] = 100.0  # w
        raw_out[0, 3, 0] = 200.0  # h
        raw_out[0, 4, 0] = 0.90   # person score

        mock_session.run.return_value = [raw_out]
        mock_session_cls.return_value = mock_session

        detector = YoloDetectors(person_threshold=0.35)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        people = detector.people(frame)

        self.assertEqual(len(people), 1)
        box, score = people[0]
        self.assertAlmostEqual(score, 0.90, places=2)
        self.assertTrue(0.0 <= box[0] < box[2] <= 1.0)
        self.assertTrue(0.0 <= box[1] < box[3] <= 1.0)

    @patch("vision.detectors.require_models")
    @patch("vision.detectors.model_path")
    @patch("cv2.FaceDetectorYN.create")
    @patch("onnxruntime.InferenceSession")
    def test_faces_empty_returns_empty_list(self, mock_session_cls, mock_yn, mock_model_path, mock_require):
        mock_face_detector = MagicMock()
        mock_face_detector.detect.return_value = (0, None)
        mock_yn.return_value = mock_face_detector

        detector = YoloDetectors()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        faces = detector.faces(frame)
        self.assertEqual(faces, [])


if __name__ == "__main__":
    unittest.main()
