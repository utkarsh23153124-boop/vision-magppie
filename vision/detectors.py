"""CPU inference. NanoDet decoding adapted from OpenCV Zoo (Apache-2.0).

Source: opencv/opencv_zoo, models/object_detection_nanodet/nanodet.py
Revision: 47534e27c9851bb1128ccc0102f1145e27f23f98
Changes: person-only scores/NMS, stable softmax, letterboxing and normalized boxes.
See THIRD_PARTY.md and licenses/.
"""
import cv2
import numpy as np

from .models import model_path, require_models


class Detectors:
    def __init__(self, person_threshold=0.40, face_threshold=0.80):
        require_models()
        cv2.setNumThreads(1)
        self.person_threshold = person_threshold
        self.mean = np.array([103.53, 116.28, 123.675], dtype=np.float32)
        self.std = np.array([57.375, 57.12, 58.395], dtype=np.float32)
        self.person = cv2.dnn.readNet(str(model_path("person")))
        self.person.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.person.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        self.face = cv2.FaceDetectorYN.create(
            str(model_path("face")), "", (320, 320), face_threshold, 0.3, 5000
        )
        self.anchors = []
        for stride in (8, 16, 32, 64):
            grid = np.arange(416 // stride) * stride + (stride - 1) / 2
            x, y = np.meshgrid(grid, grid)
            self.anchors.append(np.column_stack((x.ravel(), y.ravel())))

    def people(self, frame):
        height, width = frame.shape[:2]
        scale = min(416 / width, 416 / height)
        rw, rh = max(1, round(width * scale)), max(1, round(height * scale))
        left, top = (416 - rw) // 2, (416 - rh) // 2
        canvas = np.full((416, 416, 3), 114, dtype=np.uint8)
        canvas[top:top + rh, left:left + rw] = cv2.resize(frame, (rw, rh))
        normalized = (canvas.astype(np.float32) - self.mean) / self.std
        self.person.setInput(cv2.dnn.blobFromImage(normalized.astype(np.float32)))
        outputs = self.person.forward(self.person.getUnconnectedOutLayersNames())
        boxes, scores = [], []
        for stride, anchors, cls, dist in zip((8, 16, 32, 64), self.anchors, outputs[::2], outputs[1::2]):
            cls = cls.reshape(-1, 80)
            dist = dist.reshape(-1, 4, 8)
            # COCO class 0 is person. Filter before decoding for CPU efficiency.
            keep = cls[:, 0] >= self.person_threshold
            if not np.any(keep):
                continue
            logits = dist[keep]
            probabilities = np.exp(logits - logits.max(axis=2, keepdims=True))
            probabilities /= probabilities.sum(axis=2, keepdims=True)
            distances = (probabilities @ np.arange(8)) * stride
            centres = anchors[keep]
            decoded = np.column_stack((centres - distances[:, :2], centres + distances[:, 2:]))
            boxes.extend(decoded.tolist())
            scores.extend(cls[keep, 0].tolist())
        if not boxes:
            return []
        boxes = np.array(boxes)
        xywh = boxes.copy()
        xywh[:, 2:] -= xywh[:, :2]
        indices = cv2.dnn.NMSBoxes(xywh.tolist(), scores, self.person_threshold, 0.5)
        result = []
        for index in np.asarray(indices).reshape(-1):
            x1, y1, x2, y2 = boxes[index]
            box = (
                float(np.clip((x1 - left) / rw, 0, 1)),
                float(np.clip((y1 - top) / rh, 0, 1)),
                float(np.clip((x2 - left) / rw, 0, 1)),
                float(np.clip((y2 - top) / rh, 0, 1)),
            )
            if box[2] > box[0] and box[3] > box[1]:
                result.append((box, float(scores[index])))
        return result

    def faces(self, frame):
        height, width = frame.shape[:2]
        ratio = min(1.0, 640 / max(width, height))
        small = cv2.resize(frame, (max(1, round(width * ratio)), max(1, round(height * ratio))))
        sh, sw = small.shape[:2]
        self.face.setInputSize((sw, sh))
        _, faces = self.face.detect(small)
        self.last_face_image = small
        self.last_face_rows = faces
        if faces is None:
            return []
        return [((float(f[0] / sw), float(f[1] / sh), float((f[0] + f[2]) / sw),
                  float((f[1] + f[3]) / sh)), float(f[-1])) for f in faces]


class YoloDetectors:
    """YOLOv8n ONNX Runtime inference. Drop-in replacement for Detectors."""

    def __init__(self, person_threshold=0.35, face_threshold=0.80):
        require_models(kinds=("yolo_person", "face"))
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(model_path("yolo_person")),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self.person_threshold = person_threshold
        self.face = cv2.FaceDetectorYN.create(
            str(model_path("face")), "", (320, 320), face_threshold, 0.3, 5000
        )
        self.last_face_rows = None
        self.last_face_image = None

    def people(self, frame):
        height, width = frame.shape[:2]
        scale = min(640 / width, 640 / height)
        rw, rh = max(1, round(width * scale)), max(1, round(height * scale))
        pad_left, pad_top = (640 - rw) // 2, (640 - rh) // 2
        canvas = np.full((640, 640, 3), 114, dtype=np.uint8)
        canvas[pad_top:pad_top + rh, pad_left:pad_left + rw] = cv2.resize(frame, (rw, rh))

        blob = canvas.astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))
        blob = np.expand_dims(blob, axis=0)

        input_name = self.session.get_inputs()[0].name
        outputs = self.session.run(None, {input_name: blob})
        output = outputs[0]  # shape (1, 84, 8400)
        output = np.transpose(output[0], (1, 0))  # shape (8400, 84)

        # Class 0 in COCO is person (index 4)
        person_scores = output[:, 4]
        mask = person_scores >= self.person_threshold
        if not np.any(mask):
            return []

        filtered_out = output[mask]
        filtered_scores = person_scores[mask]

        cx = filtered_out[:, 0]
        cy = filtered_out[:, 1]
        w = filtered_out[:, 2]
        h = filtered_out[:, 3]

        x1 = cx - w / 2.0
        y1 = cy - h / 2.0
        x2 = cx + w / 2.0
        y2 = cy + h / 2.0

        # Un-letterbox back to original image space
        x1_orig = (x1 - pad_left) / rw * width
        y1_orig = (y1 - pad_top) / rh * height
        x2_orig = (x2 - pad_left) / rw * width
        y2_orig = (y2 - pad_top) / rh * height

        # Convert to xywh format in original pixel coordinates for NMSBoxes
        boxes_xywh = []
        for i in range(len(filtered_scores)):
            bx = float(max(0, x1_orig[i]))
            by = float(max(0, y1_orig[i]))
            bw = float(min(width - bx, x2_orig[i] - bx))
            bh = float(min(height - by, y2_orig[i] - by))
            boxes_xywh.append([bx, by, bw, bh])

        indices = cv2.dnn.NMSBoxes(boxes_xywh, filtered_scores.tolist(), self.person_threshold, 0.45)
        result = []
        for index in np.asarray(indices).reshape(-1):
            bx, by, bw, bh = boxes_xywh[index]
            box = (
                float(np.clip(bx / width, 0, 1)),
                float(np.clip(by / height, 0, 1)),
                float(np.clip((bx + bw) / width, 0, 1)),
                float(np.clip((by + bh) / height, 0, 1)),
            )
            if box[2] > box[0] and box[3] > box[1]:
                result.append((box, float(filtered_scores[index])))
        return result

    def faces(self, frame):
        height, width = frame.shape[:2]
        ratio = min(1.0, 640 / max(width, height))
        small = cv2.resize(frame, (max(1, round(width * ratio)), max(1, round(height * ratio))))
        sh, sw = small.shape[:2]
        self.face.setInputSize((sw, sh))
        _, faces = self.face.detect(small)
        self.last_face_image = small
        self.last_face_rows = faces
        if faces is None:
            return []
        return [((float(f[0] / sw), float(f[1] / sh), float((f[0] + f[2]) / sw),
                  float((f[1] + f[3]) / sh)), float(f[-1])) for f in faces]
