# Handoff validation on 8 October 2026

The existing Windows environment passed the complete Python 3.12 unittest suite:
**33 tests in 2.545 seconds, OK**. This is a reproducible code baseline, not a
showroom accuracy result.

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -v` | 33 passed |
| `python -m pip check` | No broken requirements found |
| `python -m central.download_models` | Existing NanoDet, YuNet and SFace files verified against pinned SHA-256 values |

The first test attempt encountered the execution sandbox's socket and temporary
file permissions. The same unchanged suite passed after rerunning with those
restrictions lifted. No application code change was needed.

## Coverage

- Counting: direction, re-entry, stable sides, jitter, initial appearance, stale
  tracks, long gaps, feet-based horizontal crossings and opposing people.
- Local pipeline: decode, CSV/summary output, browser metadata, stop/limit/error
  finalization, session isolation, staff exclusion without saving names, source
  validation, credential non-persistence and checksum rejection.
- Central: report day boundary/persistence, staff encryption/scope/removal,
  confirmation and ambiguity, latest-frame queue, reconnect generation and
  release, HTTP auth/CSRF and secret exclusion from responses.
- Demo: confirmed identity, face/body association, ambiguous identities,
  enrollment consent and validation, and enrollment required before start.

## Remaining validation

Docker/HTTPS startup, real showroom camera access, VPN routes, long-running
multi-camera performance, camera/lighting suitability and staff confusion rates
remain unverified. The model verification command checked cached artifacts; it
did not test a fresh download. The handoff did not open a webcam, enroll a person,
deploy an application or collect new footage.

Reproduce from the repository root after installing dependencies:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m central.download_models
```

Older validation documents record previous development stages; their smaller test
counts are historical. GitHub Actions runs the controlled suite on each push and
pull request using Python 3.12 on Windows and Ubuntu. Real-camera evaluation must
be tracked separately.
