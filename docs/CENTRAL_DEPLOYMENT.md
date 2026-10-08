# Central pilot deployment

## Current scope

Face detection, physical individual IN/OUT, and enrolled staff exclusion. Processing
runs centrally and keeps working when the dashboard closes. There is one admin
account, one server process and a persistent SQLite database. This is a pilot build,
not a validated production installation. There is no multi-tenant RBAC, horizontal
worker distribution or automatic database backup service yet.

## Architecture

Camera/NVR → private routed network → latest-frame reader → NanoDet + YuNet →
short-term person tracking → SFace staff matching → crossing classification →
SQLite → authenticated dashboard and CSV.

Each camera has a separate reader and inference worker. A one-frame mailbox drops
obsolete unread frames; reconnection starts a new tracking segment. It does not
eliminate buffering inside the camera or decoder. Workers retry failed connections
with bounded backoff. Start/Stop intent is persisted; enabled cameras are restored
on server restart. A worker model/database error is visible and requires fixing the
cause and pressing Start. No counts are fabricated during gaps.

## Staff enrolment and limitations

Upload 1–5 consenting staff portraits with exactly one clear face in each. Use the
same showroom name as the camera. Only normalized SFace templates are persisted,
encrypted with Fernet under MAGGPIE_STAFF_KEY; photos and visitor embeddings are
not saved. Removing staff removes active templates; backup retention is a separate
operator responsibility. Keep the key separate from the database backup.

A face must belong unambiguously to one visible person box. Matching uses a cosine
threshold of 0.50, a competing-identity margin of 0.08, and at least two recent
matching observations. These are initial conservative settings, not a calibrated
accuracy guarantee. A confirmed match must still be recent when the line crossing
is committed. Crossings are stored as visitor or staff; staff crossings appear in
the excluded audit total instead of visitor IN/OUT. Recognition after an event has
already been committed does not retroactively change it.

Side/rear-facing staff, small faces, masks, crowds and tracker ID swaps can cause
errors. Both entry and exit need usable faces near the line; one entrance camera
may not see faces in both directions. Validate this before selecting hardware.
No liveness/anti-spoofing is implemented. This is footfall analytics, not an access
control or employee attendance decision system.

## Server deployment (provider still to be selected)

1. Provide a Linux server with Docker Compose and a domain pointing to it.
2. Establish a private routed connection from server/container to each showroom
   camera or NVR (for example, a managed router VPN). No inference PC is required
   in each showroom, but a camera behind NAT is not automatically cloud reachable.
   Do not expose RTSP credentials/ports publicly. VPN setup is not automated here.
3. Copy deploy/.env.example to deploy/.env. Set a long random admin password,
   domain and a unique staff-encryption key. Generate a key on the server:

   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

4. Set each MAGGPIE_CAMERA_* environment variable to its authorized RTSP/HTTP URL.
   Dashboard configuration holds only that variable's name. Escape credentials
   correctly in the stream URL. Do not paste secrets in screenshots or commit .env.
5. From the repository root:

   `docker compose --env-file deploy/.env -f deploy/compose.yaml up --build -d`

6. Open https://YOUR_DOMAIN, sign in, add cameras and enroll staff. Start a camera,
   inspect Preview, then Stop and use Set line to calibrate orientation/position.
   Restart and perform manually counted walkthroughs.

Only the HTTPS proxy publishes ports (80/443); the application port stays on the
Compose network. HTTPS certificates require reachable DNS and ports. The app runs
as a non-root user; its database volume persists across restarts. This package
has not been Docker-built here because Docker is unavailable on this PC.
The basic Python HTTP service is intended behind the proxy for a controlled pilot;
load testing and operational hardening are required before a public rollout.

MAGGPIE_MAX_CAMERAS defaults to 4 as a concurrency guard, not a capacity promise.
Each camera loads its own models. Benchmark the target server with every camera
active before increasing this limit. The local prototype's FPS does not predict
cloud performance. No GPU acceleration is configured in this build.

## Development validation (not showroom deployment)

Install requirements.txt in a Python 3.12 environment and run:

    python -m central.download_models
    python -m unittest discover -s tests -v

Set MAGGPIE_ADMIN_PASSWORD (16+ characters), MAGGPIE_STAFF_KEY (Fernet key), and
optionally MAGGPIE_DATA_DIR. Then `python -m central.server --port 8010` binds to
127.0.0.1 for development. Do not reuse development passwords on a hosted server.

## Reports and operations

Daily/hourly reports use Asia/Kolkata (UTC+05:30). Event time is when the server
receives/decodes the frame, not verified camera exposure time. Counts persist across
worker and server restarts; net flow is not guaranteed occupancy. Multiple cameras
must not cover the same crossing unless duplication is explicitly accounted for.
The dashboard combines physical crossings, not unique visitors or family groups.

Preview refreshes roughly once per second for calibration; it is not a smooth CCTV
viewer. The overlay's IN/OUT belongs to the current tracker segment, whereas the
dashboard reports durable visitor totals and excluded staff crossings separately.
A stale preview is hidden after five seconds. Stored connection transitions expose
gaps; the latest 100 transitions for a report day are shown.

Configure encrypted, tested database backups and retention before live operation.
For a simple consistent backup, stop the service, copy the complete database data
volume, then start it again; this creates a counting gap. Back up the staff key
securely. Never copy only a live SQLite .db file while omitting its WAL. Automated
backup scheduling, retention cleanup and key rotation/migration are not implemented.

## Validation completed and still required

27 automated tests pass: original counting plus report day boundaries/persistence,
staff encryption/scope/removal, ambiguous-match rejection, latest-frame queue,
reconnect generation and HTTP authentication/CSRF. UI login, camera creation and
missing-secret errors were checked in the browser. Actual models processed a local
HTTP MJPEG test stream through a central worker, produced a preview, and stopped
cleanly. SFace model checksum/load and same-image feature matching were checked.

These checks are not showroom accuracy validation. Still required: Docker/HTTPS
startup on the target server, actual RTSP/VPN connectivity, multi-camera load,
network/power interruption recovery, staff/non-staff confusion checks in both
directions, consented enrollment photos and manual counts under representative
lighting/crowding. Acceptance thresholds must be agreed using that pilot data.
