# Maggpie Vision

CPU-first showroom analytics using Python and OpenCV: person crossings, face
detection, and showroom-scoped staff exclusion. **Pilot software; real showroom
accuracy and hosted deployment remain unvalidated.**

**New maintainer: start with [HANDOFF.md](HANDOFF.md).** It covers the current
architecture, clean setup, configuration, data handling, verification, operational
runbook, and prioritized next steps. The current automated suite has **33 passing
tests** (8 October 2026); see [handoff validation](docs/HANDOFF_VALIDATION.md).

| Mode | Start | Purpose |
|---|---|---|
| Central pilot | `python -m central.server --port 8010` | Persistent counts, camera workers, staff enrollment, authenticated dashboard |
| Laptop demo | `start_demo.bat` after `setup_demo.bat` | Consenting friends, webcam name overlays and staff-excluded crossings |
| Original local prototype | `start_web.bat`, `start.bat`, or `run.py` | Local physical counting without staff matching |

## Fresh clone setup

Install Python 3.12. From the cloned repository, run in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m central.download_models
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Models are downloaded from a pinned upstream revision and checksum-verified.
The clone does not include models, portraits, recordings, credentials, databases,
or local outputs. For the demo, create `demo_photos/PersonName/` yourself and follow
[the photo instructions](demo_photos/README.md). Central service configuration is
documented in [HANDOFF.md](HANDOFF.md#central-development-setup).

## Current release

**Friends/laptop demo:** open `start_demo.bat`, then use
http://127.0.0.1:8020. Add portraits to `demo_photos/Name/`, confirm consent, and
press Import photos before starting the webcam. See [short demo steps](docs/simple/06_FRIENDS_DEMO.md).
This demo adds on-screen names/Unknown and staff-excluded crossing counts;
the older `start_web.bat` interface does not include these demo features.

Current direction: **central server**, with face detection, individual IN/OUT and
showroom-scoped staff exclusion. Cloud provider is not selected; the application
has not been deployed. Start with [central deployment](docs/CENTRAL_DEPLOYMENT.md) and the
[short status](docs/simple/05_CENTRAL_VERSION.md).

The original local prototype remains below for development and comparison.

## Original local prototype

Face detection and physical IN/OUT footfall counting, designed CPU-first.

## Start on Windows

For the **browser interface**, run `start_web.bat`, then open http://127.0.0.1:8001.
It uses the same local detection engine and binds only to this PC. Choose the sample
clip, a full local video path, Webcam (browser permission), or an authorized camera stream.
For webcam, press Start and allow camera access in Chrome. No camera index is
needed; JPEG frames go only to the local server and are not saved. Closing the
webcam tab releases the camera; a missing feed times out after 15 seconds.
Press Start to process and Stop to save. Each start resets the session counts.
Keep the server running while using the browser. Closing the browser does not stop
counting; press Stop first. The desktop interface is also available below.

1. Python 3.12 is the tested version. On a new PC, run **setup.bat** once with internet access.
2. Double-click **start.bat**.
3. Choose **Video file**, **Webcam** (`0` usually), or **Camera stream** (authorized RTSP/HTTP URL).
4. For a video, Browse shows its first frame. Set the line orientation, position and IN direction.
5. Press **Start counting**. Press **Stop** to finish and save.

Install dependencies and verified models using setup before running a fresh clone. After setup, inference needs no cloud/internet; an IP camera still needs local network access. No camera opens until you start it.

## What the numbers mean

- **Entries / exits:** observed person crossings, not face detections per frame.
- **Faces now:** faces visible in the current processed frame, not unique people.
- **Net IN − OUT:** signed flow since this session started. It is **not verified occupancy**.
- Green boxes = people; blue boxes = faces; yellow arrow = IN.
- For horizontal lines, the green point at the bottom of a person box must cross. Put the line on the visible floor across the doorway, with space to observe both sides.
- Each Start creates a new session. Staff and repeat visitors are counted. Family members count individually in this version.

No staff recognition, daily identity deduplication, group counting, central dashboard or automatic stream reconnection in v0. A failed stream stops with a visible status; fix it and start a new session. It does not manufacture counts for the blind interval.

## Saved results

`output/<session>/events.csv` stores one row per confirmed crossing, including direction, temporary track ID, video/elapsed source seconds and UTC processing time. For recorded video, processing time is **not** the original capture date.

`summary.json` stores counts, settings, throughput and completion status. Counts are checkpointed periodically and finalized on Stop/end/error; abrupt power loss may leave a stale summary, but previously flushed CSV events remain available. No source URL, face image, embedding or video is stored. Local credentials entered in the desktop app are not persisted.

## Command line / headless

```powershell
.\.venv\Scripts\python.exe run.py --source "C:\videos\entrance.mp4" --axis vertical --position 0.5
.\.venv\Scripts\python.exe run.py --source 0 --preview
.\.venv\Scripts\python.exe run.py --source "C:\videos\entrance.mp4" --reverse --max-frames 300
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`--reverse` makes IN upward (horizontal line) or leftward (vertical line). Use the desktop masked stream input or `MAGGPIE_SOURCE` environment variable instead of putting credential-bearing URLs in shell history.

## Scope and limitations

This is a lightweight baseline using [OpenCV Zoo](https://github.com/opencv/opencv_zoo): NanoDet person detection, YuNet face detection, and a simple short-term spatial tracker with stable-side crossing logic. See [THIRD_PARTY.md](THIRD_PARTY.md) for licences and model provenance.

The tracker can swap IDs in crowds/occlusion. Hidden feet, small people, poor lighting, low frame rate or fast crossings can miss counts. Tracks first seen on the line need clear observations on one side before counting. Long gaps reset track continuity rather than infer unseen crossings. CPU throughput depends on the actual PC; the app does not promise real-time operation on every low-end device.

Video files are analysed as fast as the PC allows, using source-frame time for tracking. Live inputs use elapsed capture time. Offline video supports constant-frame-rate timing; variable-frame-rate footage may have approximate event times. Keep the camera fixed; stop and reconfigure if it moves.

Test with a representative entrance recording and a manual count before operational use. No showroom recording was supplied during development.

Historical future scope: [implementation plan](docs/IMPLEMENTATION_PLAN.md). Its local-per-showroom architecture predates the current central release. Use [the handoff](HANDOFF.md) for current scope and priorities. Short requirements: [docs/simple](docs/simple/02_REQUIREMENTS.md).

## Webcam preview performance

Browser webcam preview plays directly from the camera. Detection boxes and counts
update independently at the CPU inference rate shown as AI FPS. Boxes can trail
fast motion and disappear if the latest result is older than 500 ms. Webcam mode
returns box coordinates instead of encoding and downloading annotated JPEGs.
The one-frame input queue keeps the latest frame instead of building a backlog.
This does not make inference run at the camera frame rate; fast crossings and
crowds still need validation on the intended PC and camera.

## Licensing

Third-party notices and model provenance are in [THIRD_PARTY.md](THIRD_PARTY.md)
and `licenses/`. No project-wide license has been selected for the original
application code; public repository visibility does not grant an open-source
license. The owner should choose a license before inviting reuse or distribution.
