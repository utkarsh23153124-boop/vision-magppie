# Maggpie visitor analytics — requirements and decision questionnaire

**Historical discovery record:** local processing per showroom was later replaced
by central processing. Use [HANDOFF.md](../HANDOFF.md) for current implementation
and release scope; unanswered business questions below remain discovery items.

Short version: [Confirmed Q&A](simple/01_CONFIRMED.md) · [Requirements](simple/02_REQUIREMENTS.md) · [Pending questions](simple/03_PENDING_QUESTIONS.md).

Priority update (18 September): showroom name/city and reporting hours can be configured later. Only the entrance view/coverage is needed initially, not a full showroom plan. Target low-spec CPU-first operation; collect detailed PC specifications for deployment benchmarking rather than treating them as a prerequisite for starting the prototype.

Prepared: 18 September 2026.
Purpose: collect the inputs and business decisions needed to build, validate, and deploy the showroom pilot.
Related design: [Implementation plan](IMPLEMENTATION_PLAN.md).

Status: discovery checklist. Recommended defaults below are proposals, not approved decisions. An unanswered question is not approval. No staff/customer biometric collection or deployment has been performed.

## 1. Decisions already established

- One family/client party should count as one client group, not one client per person.
- Staff must be excluded from customer counts; staff face enrolment is the intended method.
- A returning customer/group within the same day should not add another unique client group.
- The next day should count as a new visit; long-term returning-customer recognition is not required for the initial scope.
- Local processing should run on a separate computer at each showroom.
- Reporting should cover daily/hourly footfall, live occupancy, and showroom comparisons.

Same-door entry/exit is the current design assumption and still needs site verification. Central staff management with showroom assignments is the proposed architecture, not an additional user-confirmed business rule. Pilot scope, correction policy, identity retention, and numerical acceptance targets remain open.

## 2. Inputs to arrange first

| Input | What to provide | Owner / purpose |
|---|---|---|
| Pilot site | Showroom name/city, operating hours, on-site contact | Business: choose the first installation |
| Camera inventory | Camera and DVR/NVR brand/model, entrance channel, camera count | Installer/IT: determine supported stream access |
| Entrance layout | Rough plan or placement photos, all entry/exit routes, approximate dimensions | Operations: check coverage and calibration |
| Original sample footage | Start with 20–30 minutes containing entries, exits, groups and staff; add varied conditions later | Authorized company contact: initial feasibility, not full accuracy proof |
| PC specification | OS/version, CPU, RAM, GPU if any, free storage, other workloads, uptime | IT: processing benchmark and deployment |
| Network information | PC-to-camera/NVR connectivity, wired connectivity availability, restrictions | IT: connection and recovery planning |
| Reference observations | Which people form a party, which are staff, actual entries/exits | Showroom reviewer: reliable evaluation labels |

Do not send camera passwords in chat, spreadsheets, or repository files. Configure authorized credentials locally using protected storage. Do not collect all staff photos before an enrolment and data-handling process is agreed.

## 3. Questions to resolve before dependent work

Priority meaning:

- Start: resolve before fixing pilot scope or connecting/collecting the relevant data.
- Feature: resolve before implementing that business behaviour; unrelated work can continue.
- Rollout: resolve before live operational use or expansion.

### A. Pilot, budget, and physical setup

| ID / priority | Question | Proposed default / consequence |
|---|---|---|
| A1 / Start | Which showroom is the pilot, how many centres are planned later, and how many entrances does each have? | One showroom, one fully covered entrance first; additional routes must be accounted for |
| A2 / Start | What are camera/NVR models and PC specs, and can the PC reach the entrance stream? | Audit existing equipment before selecting models or buying hardware |
| A3 / Start | Does the camera show the full doorway and usable faces in representative lighting? Can its position be changed? | Inspect footage; define a fallback if recognition evidence is inadequate |
| A4 / Start | Who can authorize footage access, configure stream credentials/networking, and install the local service? | Named IT/installer and showroom contacts; avoid credential sharing through the questionnaire |
| A5 / Start | What is the pilot budget, recurring-cost limit, and desired delivery date? | Include hardware, model/vendor licences, hosting, installation, and support; no unverified fixed-cost promise |
| A6 / Feature | If existing imagery fails, may we reposition a camera, add a camera/depth counter, or use an assisted workflow? | Benchmark first; obtain the chosen hardware/workflow decision before dependent implementation or purchase |
| A7 / Feature | Is a custom system required, or can a vendor counter/API be used if it passes the same scenarios? | Keep both options open during audit; verify event access rather than assuming raw depth/tracks are exposed |

### B. What constitutes a client and a new party

| ID / priority | Question | Proposed default / consequence |
|---|---|---|
| B1 / Feature | Should deliveries, contractors, cleaners, security, and other noncustomer visitors be excluded? | Maintain explicit reviewable noncustomer categories; do not assume every unknown person is a client |
| B2 / Feature | For a new party, is crossing the entrance enough, or must someone engage with a salesperson/register an enquiry? | Count completed entry for walk-in footfall; keep qualified enquiries separate if requested |
| B3 / Feature | A known customer returns with a new companion: same client party or a new enquiry? | Review rather than automatically attaching all companions to an old group |
| B4 / Feature | Members of a family enter separately, or a member returns alone: who can confirm/add them to the existing group? | Automatic association only when evidence supports it, with staff correction for ambiguous cases |
| B5 / Feature | An architect/designer returns with a different client family: should that be a new party despite the returning individual? | Proposed: new client party; separate professional companion from the buying-party identity |
| B6 / Feature | If the same party visits two Maggpie showrooms on the same day, should both showrooms count it? | Yes, one per showroom; the company total is a sum of showroom visits, not unique people across the chain |
| B7 / Feature | Does 'same day' mean local calendar date or a trading day that may extend after midnight? | Local calendar date unless business hours require a defined trading-day cutoff |
| B8 / Feature | Should children/companions be included in individual occupancy, and should staff occupancy be shown separately? | Count actual people in physical occupancy; retain client-group and staff metrics separately |

### C. Group accuracy and correction workflow

| ID / priority | Question | Proposed default / consequence |
|---|---|---|
| C1 / Start | Is estimated grouping with staff correction acceptable, or is unattended operation a hard requirement? | Assisted pilot; test whether unattended operation can meet the required accuracy |
| C2 / Feature | Who can confirm/merge/split groups, and will review happen live or at closing? | Designated showroom reviewer; closing review unless immediate counts drive an operational decision |
| C3 / Feature | How much review time per day is acceptable, and which error is worse: extra clients or missed clients? | Agree a review-effort budget and measure false merges and false splits independently |
| C4 / Feature | What should reports do with unresolved cases, and can historical totals change after correction? | Show pending/estimated status; preserve audit history and recalculate affected periods |
| C5 / Feature | Is there an existing visitor register, CRM enquiry record, receptionist workflow, or sales log we can use for group confirmation? | Link to an existing process where possible; sales transactions alone are not ground truth for all walk-ins |

### D. Staff, permissions, and biometric handling

| ID / priority | Question | Proposed default / consequence |
|---|---|---|
| D1 / Feature | How many staff per showroom, and which staff visit multiple branches? Who maintains active/left/transferred status? | Central staff IDs and multi-showroom assignments; local copies only where assigned |
| D2 / Before enrolment | Who authorizes and carries out staff face enrolment and removal? | Controlled enrolment UI with recorded authorization and named admin |
| D3 / Before visitor identity processing | What company-approved notice/consent, access, purpose, and data-handling requirements apply to visitor face matching? | Establish the approved process before live biometric matching; physical counting can be evaluated independently |
| D4 / Before retention implementation | Can original enrolment/review photos be retained, for how long, and where? What is the visitor-template expiry rule? | Keep visitor templates local for the agreed day; minimize originals and review evidence; cover caches/backups too |
| D5 / Feature | Must staff be recognized automatically in every branch or only in assigned/temporary branches? | Explicit assignments, including temporary visits; display sync freshness and pending revocations |

These are requirements questions, not an assertion that one particular consent mechanism establishes legal compliance. Company policy and any applicable review must define the actual operating requirements.

### E. Dashboard, installation, and support

| ID / priority | Question | Proposed default / consequence |
|---|---|---|
| E1 / Feature | Who needs access: branch staff, managers, head office, external support? What may each role view or edit? | Branch-scoped reviewers; head-office reporting/admin; restricted biometric access |
| E2 / Feature | Which exports/integrations are essential for v1: CSV/Excel, CRM, scheduled reports, or only the dashboard? | Dashboard and basic export first; specify field definitions and required integration endpoints |
| E3 / Feature | How fresh must central counts be, and should hourly charts show first-time parties or all entry events? | Show both as separate metrics; unique parties attributed to first arrival; display last-sync time |
| E4 / Rollout | Is company-approved cloud hosting available, or must the central service be on-premises? | Decide with IT; camera feeds and transient visitor templates stay local by default |
| E5 / Rollout | Can the PC remain on during opening hours, and who handles sleep, power loss, updates, disk space, and camera changes? | Auto-start service and health monitoring; assign responsibility instead of assuming availability |
| E6 / Rollout | Who receives service-failure alerts and handles support, template-sync failures, and occupancy reconciliation? | Named operations contact, documented recovery steps, and visible stale/uncertain status |

### F. Pilot sign-off

| ID / priority | Question | Proposed default / consequence |
|---|---|---|
| F1 / Start | Who will label actual groups and provide a manual reference during the pilot? | A showroom reviewer plus staged known scenarios; do not infer true family membership from video alone |
| F2 / Before scored pilot | What acceptance thresholds are required for crossings, staff exclusion, repeat matching, group count, and review workload? | Use separate metrics; numerical targets in the implementation plan are proposals, not guarantees |
| F3 / Before scored pilot | How many representative days/events and difficult scenarios must be evaluated, and who signs off expansion? | Agree coverage and adequate sample sizes; separate tuning footage from held-out evaluation |

## 4. Practical answer template — start with these

You do not need to answer every implementation question at once. Start with the items that materially change the first milestone:

```text
Pilot showroom / city:
Approximate number of future showrooms:
Entrances and entrance cameras:
Camera + DVR/NVR model:
PC specs and operating hours:
Sample footage available: Yes / No / To arrange
IT/installer and showroom reviewer available: Yes / No / To arrange
Pilot budget / recurring-cost limit:
Desired pilot date:
Group corrections acceptable: Yes / No / Needs discussion
Architect/designer returning with a different client: New party / Needs discussion
Existing visitor register or CRM:
```

If hardware facts are unknown, provide model-label images/specifications through the normal conversation or arrange a site audit; no need to guess. Biometric authorization and retention decisions remain required before that dependent work, even if an early non-biometric counting prototype is underway.

## 5. Decision record format

For each question record: ID, answer, owner, decision date, status (open/proposed/confirmed), affected feature, and reason. Maintain one approved configuration per showroom, with company-wide business definitions where appropriate. Any later rule change should be versioned so historical reports remain interpretable.
