# Open-source components

This prototype uses OpenCV Zoo models rather than cloning an entire counting application.
Central staff matching additionally uses OpenCV Zoo SFace under Apache-2.0;
licence: `licenses/SFace-Apache-2.0.txt`. The approximately 39 MB model is pinned to
the same revision below. SHA-256:
`0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79`.
Model filename: `face_recognition_sface_2021dec.onnx`.
No upstream benchmark accuracy is claimed for a showroom installation.
Upstream revision: `47534e27c9851bb1128ccc0102f1145e27f23f98`.

| Component | Source | Upstream licence |
|---|---|---|
| NanoDet person detection model / decoder basis | [OpenCV Zoo NanoDet](https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/object_detection_nanodet) | Apache-2.0; copy in licenses/NanoDet-Apache-2.0.txt |
| YuNet face detection model | [OpenCV Zoo YuNet](https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet) | MIT; copy in licenses/YuNet-MIT.txt |

NanoDet upstream contributor: Sri Siddarth Chakaravarthy (OpenCV GSoC 2022), with the NanoDet project by RangiLyu. The decoder in `vision/detectors.py` adapts the upstream equations and normalization; modifications are noted in that file.

Model downloads are pinned and SHA-256 checked against the upstream Git LFS identifiers. Models total approximately 4 MB. Library dependencies retain their own packaged licences (OpenCV, NumPy, Pillow). This document does not relicense those components or grant third-party rights beyond their terms.
