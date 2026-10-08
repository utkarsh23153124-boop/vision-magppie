# Central version — current status

- Scope: face detection, individual IN/OUT, staff face exclusion.
- One central dashboard; multiple showroom cameras and saved daily/hourly reports.
- Staff: consented enrolment, encrypted templates, showroom-wise matching, removal.
- Unclear staff faces remain included; this needs real-camera validation.
- Camera disconnect: retries, visible connection status; missing time is not recovered.
- Local showroom PC deployment cancelled. Cloud provider still pending.
- Docker/HTTPS deployment files added; Docker build not tested on this PC.
- Tests: 33 passed on 8 October 2026. Earlier browser/login and local HTTP stream checks are historical; see [handoff validation](../HANDOFF_VALIDATION.md).
- Next: hosting/domain, private camera network route, RTSP details and staff portraits.
- Family grouping and same-day repeat exclusion are outside this release.
