# Basic version validation — 22 September 2026

## Completed

- Python 3.12.3 isolated environment; pinned dependencies installed; `pip check` passes.
- Model SHA-256 checks match the pinned OpenCV Zoo Git LFS metadata.
- 20 automated tests pass: crossing direction, stable-side filtering, jitter, initial appearance, return crossings, stale/unobserved tracks, separated opposite-direction people, decode/export, Stop, frame limit, session isolation, error finalization, URL non-persistence and checksum rejection.
- Real NanoDet and YuNet inference on a public OpenCV sample image returns people and a face. Blank image returns neither.
- Full headless model pipeline on an 84-frame controlled translated-image video: **1 IN, 1 OUT**, completed, peak visible faces 1. Approximately **6.94 processed FPS** in this one development-machine run, not a minimum hardware guarantee.
- Desktop application constructs and its Start -> preview -> Stop -> save -> controls restored flow passes a local Tk smoke test. No webcam/real camera was opened.
- Python compilation succeeds.

## What this does not prove

The controlled video moves a public image across a canvas. It tests wiring, inference and crossing flow, not real-world tracking accuracy. Automated crossing tests use controlled detections to isolate state-machine behaviour. The GUI check is programmatic, not a full manual usability audit.

No showroom footage has been provided. Actual doorway accuracy, crowds/occlusion, real webcam/RTSP compatibility, live buffering, low-spec-PC throughput and long-running stability are unverified. A short-term spatial tracker can change identities in crowded views.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe run.py --source samples/controlled_crossing.avi --axis vertical --person-threshold 0.55
```

The last command requires the locally generated smoke-test video; `samples/` is ignored and is not an application dependency. Public image used for the developer smoke test: [OpenCV 4.11.0 samples/data/messi5.jpg](https://github.com/opencv/opencv/blob/4.11.0/samples/data/messi5.jpg). Test imagery is not bundled for redistribution.
