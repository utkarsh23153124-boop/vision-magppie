# Maggpie showroom visitor analytics — implementation plan

**Historical design:** the local-per-showroom architecture below predates the
current central-server pilot. Staff exclusion and central reporting now exist;
grouping and same-day deduplication remain future work. Start with the
[8 October 2026 handoff](../HANDOFF.md) for current scope and next steps.

Status update, 22 September 2026: a basic local face-detection and person-crossing prototype is implemented; see [README](../README.md). It uses NanoDet + YuNet with a simple tracker, not the full model stack proposed below. Models and dependencies are installed in the development workspace. Staff recognition, group counting, daily deduplication, central reporting and showroom deployment remain future work. No real showroom camera has been connected.
Prepared: 17 September 2026.

Discovery inputs and unresolved decisions: [Requirements and decision questionnaire](REQUIREMENTS_AND_DECISIONS.md), added 18 September 2026. Proposed defaults are not treated as approved answers.

## 1. Outcome and decisions

Build one centrally managed application with a local processing service per showroom. Start with one showroom and one entrance. Reuse the existing CCTV/NVR feed if the audit confirms usable coverage. Support a dedicated 3D counting device through an adapter only after verifying its actual output and licensing.

The highlighted stereo sensor is an alternative input device, not a requirement for the baseline. A commercial stereo counter may expose only processed counts, not stereo images or person tracks. Buying one does not automatically make its depth data available to our software.

Confirmed business requirements:

- A family/buying party counts as one client group.
- Registered staff are excluded from customer metrics.
- Recognized returns within the same local date do not add another client group.
- The next local date starts a new customer identity namespace.
- Each showroom has a local PC; central reporting covers all showrooms.

Working scope decisions:

- Updated 18 September: target low-spec PCs with CPU-first processing; establish minimum supported hardware by benchmarking, not by promising support for every PC. Showroom name/city are not prototype prerequisites. Inspect the entrance view; a full showroom floor plan is not required for the one-door pilot.
- Same-door entry/exit is the initial design assumption and needs verification at the pilot site.
- Proposed staff management is central enrolment with one or more showroom assignments and relevant local template copies.
- Uniqueness is per showroom per local date, not across the entire company.
- Occupancy counts individual visitors; daily client reporting counts groups.
- Every physical crossing remains an event, including repeated entries.
- Group membership is an estimate unless confirmed; uncertainty is not converted to a definite family relationship.
- Non-staff does not necessarily mean customer. Delivery/vendor visits need an optional manual exclusion category.
- Returning people with new companions, conflicting previous groups, and delayed family arrivals are review cases until a business rule is established.
- No next-day customer identification, demographic classification, sales attribution, or custom stereo hardware development in the initial release.

## 2. Hardware paths and decision gates

| Path | Input | What we implement | Gate |
|---|---|---|---|
| A — existing CCTV | RTSP/NVR video | Detection, tracking, recognition, groups, reports | Doorway coverage and face quality are adequate |
| B — commercial 3D counter | Supported device/server API | Vendor adapter and reports; additional identity processing only if association is feasible | Exact metrics, identifiers, timestamps, latency, API fees, and offline behaviour verified |
| C — developer depth camera | SDK RGB/depth data | Depth acquisition, coordinate calibration, detection and application pipeline | Existing view fails and an SDK-based device is demonstrably preferable |

Do not implement all three paths initially. Implement A unless the audit favours B. Keep a small input interface so a later adapter does not require rewriting the reporting layer.

For B, explicitly distinguish:

1. Aggregate totals only: suitable for vendor reporting; cannot reconstruct individual membership or implement custom same-day identity matching from these totals.
2. Individual/group events with stable IDs and timestamps: may support some integration; document the lifetime and scope of IDs.
3. Tracks/positions or synchronized RGB/depth: richer processing may be possible, subject to access and calibration.

Never add vendor group totals to custom group totals for the same entrance. Configure one authoritative counting source per entrance and metric. Comparative pilot results remain separate.

If combining an overhead sensor with a face-facing camera, require synchronized clocks, shared coverage, calibrated geometry, and tested one-to-one association. Timestamp proximity alone is insufficient in crowds. Without reliable association, keep the measurements separate or use review.

If path C becomes necessary, use a supported synchronized/calibrated stereo SDK. Two arbitrary CCTV cameras are not a drop-in depth sensor. Raw stereo processing requires camera calibration, rectification, valid disparity, depth conversion, and a floor coordinate frame. Prefer the manufacturer's calibrated output. [OpenCV calibration reference](https://docs.opencv.org/4.8.0/d9/d0c/group__calib3d.html)

## 3. Architecture

```text
Showroom
  CCTV/NVR -> capture -> detector/tracker -> crossing events
                            |                    |
                            +-> face matcher ----+
                            +-> group resolver --+-> visit resolver
                                                      |
                                             local event database
                                               /             \
                                       review UI          sync outbox
                                                              |
Central                                                       v
  staff/configuration management <-> authenticated API -> PostgreSQL
                                                       -> dashboard

Optional: vendor adapter -> normalized events OR separate aggregate metrics
```

Use an edge worker, local API, and background sync process. Keep a modular central application; do not introduce a distributed service fleet for the first pilot.

Proposed stack:

- Python for inference and processing; FFmpeg/OpenCV for video access.
- Small YOLO person detector candidate and ByteTrack baseline; compare alternatives only when measured failures justify it.
- SCRFD face detector and commercially authorised ArcFace-based embeddings/SDK as candidates.
- ONNX Runtime or another supported runtime after hardware/model compatibility benchmarking.
- FastAPI for local/central APIs, SQLite with controlled writes for edge data, PostgreSQL centrally.
- React/TypeScript review and reporting interface, served by the application.
- OS-native service installation on the actual showroom OS; Windows Service if showroom PCs are Windows.

Pin versions and record model checksums, preprocessing, embedding dimensions, and calibration versions. Staff enrolment creates templates; it does not retrain a model per employee.

Commercial use is a model-selection gate: Ultralytics offers AGPL/Enterprise terms; InsightFace code and supplied pretrained weights have different licences. Do not assume a research-weight licence covers a company pilot. Confirm rights before downloading/using those weights for the business. [Ultralytics](https://www.ultralytics.com/license), [InsightFace](https://github.com/deepinsight/insightface#license)

## 4. Work packages in implementation order

### P0 — site and data audit

Collect camera/NVR model, supported stream access, entrance channel, PC CPU/RAM/GPU/OS, mounting position, door dimensions, alternate entrances, and network topology. Inspect representative permitted clips from different lighting and traffic conditions.

Measure usable face observations, visibility of feet/ground contact, occlusions, motion blur, glare, stream stability, and achievable processing latency. Confirm credential handling without putting secrets in source or logs.

Obtain labelled examples of individual crossings, staff movements, group membership, and staged same-day returns. Group ground truth comes from staff observation or staged known parties, not guessing relationships from video.

Deliverables: site assessment, dataset manifest, manual labels, PC benchmark, chosen hardware path, licence register, initial acceptance criteria. Gate: usable input and a supported integration route. If recognition is not feasible, specify the camera adjustment/additional view or an assisted operating mode before proceeding.

### P1 — event foundation and replay harness

Implement recorded-video input first, with timestamps and configurable playback speed, then add live capture. Define normalized crossing, identity-decision, group-decision, correction, health, and source-aggregate records.

Create schema migrations, an event journal, idempotency keys, bounded processing queues, and a small replay viewer. Simulate duplicate messages, out-of-order updates, process restarts, and incomplete tracks.

Deliverable: reproducible processing of a clip into durable events. Gate: restart and replay do not double-count already committed events; new live tracks after a restart are not assumed to be previous tracks.

### P2 — capture, tracking, and physical counting

Connect to the supported stream using restricted credentials and stable addressing. ONVIF can assist discovery/configuration where supported; verify the device rather than assuming protocol support. [ONVIF Profile T](https://www.onvif.org/profiles/profile-t/)

Configure outside, doorway, and inside zones. Implement:

```text
OUTSIDE -> DOORWAY -> INSIDE = entry
INSIDE -> DOORWAY -> OUTSIDE = exit
OUTSIDE -> DOORWAY -> OUTSIDE = no completed entry
```

Require stable side observations/hysteresis. Track bottom-centre ground-contact estimates when visible. Mark tracks starting midway through a crossing or lost at the threshold as ambiguous rather than inventing a direction.

Include source session IDs in track references. Detect stale/frozen frames as well as disconnected sockets. Log gaps and reset short-term tracking after material discontinuities. Do not mark a blind period as zero visitors.

Use bounded queues to avoid an accumulating live-video delay. If load forces gaps large enough to jeopardize crossings, raise a degraded-counting state; dropping frames is not automatically harmless.

Deliverable: physical IN/OUT events, stream-health view, and manual comparison report.

### P3 — staff enrolment and same-day identity

Build central staff enrolment, multi-showroom assignment, versioned template sync, revocation tombstones, local encrypted template storage, and last-sync status. Test add, transfer, removal, and reconnect after a missed removal. An offline edge cannot learn a new revocation instantly.

Associate faces to person tracks using spatial and temporal evidence. Select good observations using configurable size, sharpness, pose, and occlusion gates. Do not accept the nearest face or a single weak match in a crowd.

Compare against assigned staff and the current showroom/day visitor gallery. Use calibrated thresholds, best-vs-second-best margin, and multiple observations. Keep rejected/ambiguous matches unresolved. Raw similarity is not a calibrated probability.

Staff matches require particularly conservative acceptance because a false match removes a customer. Identity results can arrive after the physical entry and revise derived counts without deleting the crossing event.

Persist daily templates and decisions across PC restart. Avoid automatically contaminating a known person's templates with uncertain matches. Do not match templates generated by incompatible model versions; re-enrol staff or regenerate from authorised retained enrolment images when needed.

Deliverable: staff exclusions and repeat-person associations with measured false matches and missed matches.

### P4 — group resolver

This is our proposed algorithm, not a claim that vendor internals are identical.

1. Exclude confidently recognized staff from customer group candidates; leave unresolved status visible.
2. Build short trajectories from entry observations, with timestamps, position quality, and direction.
3. Where possible, project foot-ground points onto a calibrated floor plane using known reference points. Do not interpret raw image pixels as metres or project head points as floor points. If feet/plane calibration are unreliable, disable metric distance claims and flag reduced confidence.
4. Evaluate candidate pairs using overlap in observation time, sustained proximity, heading agreement, speed agreement, and crossing-time separation. Missing evidence stays missing.
5. Form candidate clusters with bounded diameter and compatibility constraints; do not use unrestricted transitive proximity that can merge a queue through A-near-B-near-C chains.
6. Maintain provisional membership with hysteresis so groups do not flip every frame. Finalize after the observation window/zone exit with a maximum timeout and quality status.
7. Associate confidently returning members with previous daily groups. Do not attach all new companions because one member matched an old group. Mixed previous groups go to review.
8. Provide confirm, split, merge, add-to-existing-group, and exclude-noncustomer actions. Audit and propagate every correction.

Tune duration, distance, speed, and angle thresholds on labelled calibration footage. Keep evaluation days separate. Sparse evidence should increase review needs, not generate an unearned high-confidence result.

The vendor comparison is relevant: FootfallCam documents grouping through 3D proximity and trajectory filtering and says it does not establish social relationships. That supports testing behavioural grouping, not promising exact family recognition. [Vendor grouping documentation](https://www.footfallcam.com/people-counting/knowledge-base/chapter-15-counting-modules/)

Deliverable: estimated groups, labelled uncertainty, member association, and correction workflow. Gate: business count errors and review effort meet the pilot criteria.

### P5 — reporting, central sync, and operations

Show daily new client groups, hourly first arrivals, individual entries, repeated entries, occupancy quality, pending reviews, and camera/service health. Distinguish estimates from confirmed records.

Occupancy is a net crossing estimate with an opening baseline. Identity-specific presence may be unresolved even when a crossing direction is known. Do not silently clamp contradictions into a clean number; flag and reconcile. Missed-door coverage or outages invalidate a precise live occupancy claim.

Write event and outbox entry in one local transaction. Central ingestion deduplicates by stable event ID; edge retries until acknowledged. Give corrections their own IDs and ordered revisions. Return IDs acknowledged and do not rely on one global timestamp watermark for all devices.

Use an edge agent as the authoritative sequencer for local inference and correction state in v1. Central admin corrections can be queued as commands to that edge and displayed as pending while it is offline. Avoid two independent writers overwriting group membership without revision checks.

Persist staff/configuration sync revisions independently from event sync. Record event time, receipt time, UTC timestamp, showroom timezone, and local date. Day rollover must survive restart; purge expired customer templates before loading them on startup. Resetting daily identity does not reset physical occupancy or create a synthetic entry for people already inside; carry physical presence uncertainty separately and allocate a new daily identity only under the new day's rules.

Deliverable: centrally visible, correctable reports and a tested disconnected operating mode.

### P6 — shadow pilot and staged rollout

Run alongside a manual reference over representative business days. Include scripted edge cases and real walk-ins. Review failures by component rather than optimizing only a net daily total. Freeze model/configuration versions during a scored evaluation period.

Ship one site first, then a small additional cohort. Verify each entrance's calibration; do not copy pixel coordinates from one camera to another. Keep versioned site configuration, signed update packages, database migration compatibility, rollback instructions, and a support runbook.

## 5. Data model and API contracts

Core records:

| Record | Key facts |
|---|---|
| Company/showroom/camera | Scope, timezone, authoritative source, operating hours |
| Staff/assignment/template | Staff ID, showroom access, template/model version, revocation |
| Crossing | Event ID, source/session/track, direction, time, evidence quality |
| Daily person | Showroom, local date, unresolved/resolved identity, expiring templates |
| Visit session | Repeated physical attendance periods; exit may be unresolved |
| Daily group/membership | Group ID, members, estimated/reviewed state, revision |
| Correction | Actor, reason, target, expected revision, resulting revision |
| Health/gap | Missing observations, degraded processing, sync freshness |
| Outbox | Event ID, payload version, acknowledgement/retry state |
| Vendor aggregate | Metric definition, source interval, completeness and revision |

Keep source aggregate records separate from individual crossing events. An aggregate API does not imply member-level drill-down exists.

Proposed endpoints (our application contracts, not vendor endpoints):

```text
POST /v1/events/batch
GET  /v1/showrooms/{id}/configuration
GET  /v1/showrooms/{id}/staff-changes?after_revision=...
POST /v1/staff
POST /v1/staff/{id}/enrolments
POST /v1/staff/{id}/assignments
POST /v1/groups/{id}/corrections
GET  /v1/showrooms/{id}/summary?date=...
GET  /v1/showrooms/{id}/review-queue
POST /v1/devices/{id}/heartbeat
```

Enforce company/showroom scope server-side, including template downloads and review evidence. Use device identities for edge agents and scoped human roles for administrators and reviewers. Camera credentials never appear in these report payloads.

## 6. Retention and security implementation

- Central staff templates and optional enrolment images use restricted encrypted storage; images are not public static assets or source-controlled files.
- Local templates use encryption with a key protected by the target OS, separate from the database file. SQLite by itself does not provide the required encryption.
- Visitor templates stay local by default; purge after the configured local day and on next startup if a machine was off. Aggregate historical reports remain.
- Ensure expired templates do not persist through logs, exports, replay fixtures, caches, or backups; exclude transient galleries from generic long-term backups or implement a compatible deletion strategy.
- Define a short, purpose-specific retention period for any review clips/photos; retaining evidence is optional, not automatic continuous recording.
- Record staff enrolment authorization and establish the company's visitor notice/consent and data-use requirements before live identity processing.
- Restrict central access and local ports, protect credentials in the OS secret store, and use TLS for central traffic. Do not expose camera ports to the public internet.

These are engineering requirements, not an assertion of compliance with any particular law.

## 7. Validation and proposed acceptance gates

Candidate quality targets below are planning targets, not achieved results or guarantees. Confirm operational tolerance in P0 and report sample counts and uncertainty. A small zero-error demo does not prove a low error rate in production.

| Area | Proposed gate / measurement |
|---|---|
| Crossing detection | At least 98% precision and recall separately for entry and exit on held-out representative footage |
| Staff exclusion | Report staff recall and customer false-exclusion rate; investigate every observed customer exclusion before rollout |
| Same-day matching | Candidate target: 99% accepted-match precision and 95% repeat recall; report end-to-end recall including unusable faces |
| Group counting | Report exact party accuracy, false merges/splits, count error, and review fraction; assisted mode remains if unattended operation is not validated |
| Performance | Proposed p95 physical-event availability under 5 seconds at the chosen stream workload; group finalization latency reported separately |
| Sync/replay | Zero additional events from replaying an already acknowledged batch; count preserved through tested crash/retry scenarios |
| Offline durability | Events/templates survive tested restart and network outage; expired identities are not resurrected |
| Occupancy | Compare physical truth periodically; show uncertainty after observation gaps |
| Data isolation | No cross-company/showroom access outside assigned scope |
| Operations | Full opening-hours soak test on the actual PC without sustained backlog or silent stream gaps |

Minimum scenario matrix:

- Solo arrival; a four-person party; two unrelated simultaneous arrivals.
- Family members separated in time; a queue; opposite-direction crossings; doorway U-turn.
- Staff alone; staff escort; visiting staff assigned to multiple showrooms; delivery visitor.
- Whole group returns; one member returns; returner plus new companion; two old groups combine.
- Poor light, backlight, occlusion, hats/masks, face never visible, and smaller visitors.
- Internet loss, PC restart, camera restart, frozen frames, disk pressure, clock adjustment, and local-date rollover.
- Delayed correction, duplicate correction, template revocation while offline, model-version mismatch.
- If two sensors are used: clock offset, overlapping events, failed cross-camera association, and conflicting source counts.

Test the real state machine, matching decisions, group constraints, transactional outbox, access boundaries, and retention. Avoid tests that only mirror internal implementation details.

## 8. Effort, dependencies, and ownership

Rough planning allowance for one experienced full-time engineer, timely footage/IT access, and a part-time showroom reviewer:

| Work | Engineering allowance |
|---|---|
| P0 audit and integration decision | 2–4 working days after access |
| P1–P2 foundation and footfall baseline | 1–2 weeks |
| P3 staff and daily identity | 1–2 weeks |
| P4 grouping and review | 1–2 weeks |
| P5 dashboard, sync, deployment hardening | 1–2 weeks |
| P6 shadow pilot | 1–2 calendar weeks plus measured fixes |

Approximately 6–11 weeks is a planning range for a usable pilot, not a delivery commitment. Procurement, licensing, poor imagery, unavailable labelled examples, a second-camera association pipeline, or SDK/depth development can extend it. A vendor solution meeting all acceptance scenarios could shorten custom work.

Engineering owns the application and evaluation. Showroom staff provide ground truth and review. IT/installer owns stream/network/placement access. The company owns metric definitions and biometric data-use decisions. Vendor API or model-licence dependencies should be resolved before their dependent milestones.

## 9. First implementation batch and repository layout

Do first: site inventory, sample-video replay, schema/event contracts, zone editor, detector/tracker adapter, physical crossing events, and annotated count comparison. Develop the staff gallery next. Defer full central reporting until baseline events are trustworthy.

Planned full-product layout (the basic prototype currently uses app.py, run.py, vision/, and tests/):

```text
apps/edge/             capture, inference, identity, grouping, local service
apps/api/              central staff/configuration, ingestion, reporting
apps/web/              setup, review, reports, health
packages/contracts/   versioned event/configuration schemas
config/               templates; no credentials
migrations/           local and central schema migrations
evaluation/           replay, scoring, manifests; no committed biometric data
tests/                state, sync, access, retention, scenario tests
deployment/           OS service installer, upgrade/rollback, runbook
docs/                 architecture, decisions, pilot reports
```

## 10. External evidence and vendor checks

- [FootfallCam technology](https://www.footfallcam.com/Product/Technology): stereo depth approach; does not establish raw SDK access for a purchased model.
- [FootfallCam grouping](https://www.footfallcam.com/people-counting/knowledge-base/chapter-15-counting-modules/): behavioural group inference and its limitations.
- [FootfallCam integration](https://www.footfallcam.com/Product/FootfallCam-Software-Suites-System-Integration): APIs/data export exist. Obtain an exact model/version API contract; do not infer per-person access from generic export availability.
- [ONVIF Profile T](https://www.onvif.org/profiles/profile-t/): supported streaming interoperability where device/client conformance applies.
- [OpenCV calibration](https://docs.opencv.org/4.8.0/d9/d0c/group__calib3d.html): stereo geometry for an optional SDK-based implementation.
- [Ultralytics licence](https://www.ultralytics.com/license) and [InsightFace licence](https://github.com/deepinsight/insightface#license): review exact code/weight rights before adoption.

No vendor was contacted or device ordered while preparing the plan. The later basic prototype was verified using local generated videos and a public OpenCV sample image; no staff enrolment or showroom biometric data collection has been performed.
