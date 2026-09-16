## 01 — From fibre signals to cable intelligence

Audience: technically informed executives and project stakeholders. This presentation describes the repository and recorded project evidence as of 16 September 2026. It is not a claim of a production rollout or certified event detection. Future phases are proposed, with no approved budget or delivery dates implied.

PROJECT SNAPSHOT / 16 SEP 2026

## 02 — The foundation is built. Field validation is the next gate.

Counts are the recorded 16 September 2026 snapshot, not a fresh server query. Existing 115,847 legacy events are unclassified threshold records. The 575 connections are inferred. New investigation tables and review writes are local; server class and asset migrations were previously applied.

SOURCES / docs/map-app.md · docs/masts.md · docs/event-ml.md · recorded DB snapshot

## 03 — Turn distributed measurements into actionable evidence

DAS means distributed acoustic sensing. A channel is a spatial sample along the monitored fibre. The target classes are not the RMS/variance metric identifiers in the database. Vegetation strikes are a candidate subtype of External Interference, not an implemented dedicated classifier. Ice mass, load and displacement cannot be inferred without calibration and ground truth.

SOURCES / AGENTS.md · docs/event-ml.md; operational outcomes are project goals

## 04 — One evidence chain connects signals, assets and review

React/TypeScript, MapLibre and Plotly form the frontend. FastAPI serves PostgreSQL metadata and bounded HDF5 slices. Capture accepts completed-file notifications and publishes atomic file-backed snapshots. Replay is implemented and explicitly labeled. Live operation requires independently verified acquisition time and channel mapping; notification support is not evidence of field validation. No complete raw signal array is posted as an in-memory global.

SOURCES / docs/map-app.md · src/Mapui/{api,signals,metrics,live}.py

## 05 — 579 masts anchor the asset view across four routes

Diagram generated directly from imported mast coordinates, ordered by route_position; links are illustrative inferred connections, not the actual fibre path. Route names come from the mast workbook inventory, not conflicting event-limit gids. R13 lacks M38. R06 M184–M188 lie 17.5–498.5 m from the endpoint channel; R14 M1 is about 30.1 m away. All other imported masts are within 10 m. Seven water-crossing candidates are unconfirmed and all installation types remain unknown.

SOURCES / results/masts/masts.csv · results/masts/spans.csv · docs/masts.md

## 06 — Investigate an event, a place or a recording

Unmodified screenshot of the current local application. Its Nord styling and legacy Sensnet label are retained as implementation evidence; the presentation introduces Ubeconn branding separately. The recording shown is an independent archive example, not a verified window for historical events. Map attribution is retained within the screenshot. Basemap: OpenFreeMap / OpenMapTiles / OpenStreetMap. Local review identities are self-reported; authentication is a deployment task.

SOURCE / .local/screenshots/overview.png · docs/map-app.md

## 07 — Signal amplitude and event meaning stay distinct

The local app applies header dataScale and preserves explicit header channel IDs. Fixed ten-second frames make map metrics independent of display zoom. AC RMS and absolute peak remove the window mean; band RMS integrates Welch power, with exploratory default 1–10 Hz; variance uses squared units. Display reduction retains actual extrema. Current example recordings resolve 17,010 exact positions and 8,224 bounded coordinate interpolations. Two channels outside the stored mapping remain unlocated. No signal values are interpolated or channel IDs shifted.

SOURCES / docs/map-app.md · docs/channel-mapping.md · src/Mapui/metrics.py

## 08 — The largest archive is still an unlabeled candidate set

115,847 records span 22 April–2 June 2025 and are all RMS metric events with NULL class in the inspected snapshot. Their comments do not match current threshold names, so the legacy location join cannot resolve them. Current channel metadata is dated 16 April 2026. Example archive headers suggest 16 June 2026 but original acquisition-time interpretation remains unverified. A 2026 recording cannot be attached to a 2025 event merely for visual completeness. NULL means unclassified, never normal.

SOURCES / AGENTS.md · docs/map-app.md · docs/event-ml.md · .local/verification.json

## 09 — Weather adds context once time and location are trustworthy

Stored variables are air temperature, wind speed and wind direction at Kråkern Bru and Leknes. These are collected YR forecast values, not necessarily direct measurements. The current collector uses database-default collection timestamps rather than verified forecast-validity times. The local UI only uses past rows relative to the stored event time and displays missing/stale context; this does not independently verify the original acquisition alignment. Add humidity with explicit lookup semantics, units, collector support and missing-value handling. Do not assume numeric type 4 means humidity.

SOURCES / src/weather/weather_capture.py · docs/map-app.md · docs/event-discovery.md

## 10 — Archive discovery has been exercised on real recordings

Pilot inputs: 90 approximately ten-second files, 25,236 channels, roughly 15 minutes of archive data. Fifteen 60-second temporal windows × 16 spatial blocks × 32 channels per block produce 240 feature rows. Six exploratory clusters have populations 45, 12, 23, 131, 7, 22 for IDs 0–5. Initial run 37.849 seconds, resume 0.288 seconds; max RSS 164300 KiB = approximately 160.4 MiB. Resumed feature output had identical SHA-256. These are one recorded run, not general performance guarantees. No weather join was enabled; timestamps and locations were unverified. Scores are review priorities, not class probabilities.

SOURCES / results/das-discovery-pilot-20260916/{summary,pilot-validation}.json

## 11 — The ML baseline is built; field accuracy is still unproven

No trained supervised model or measured field accuracy is supplied. The offline baseline uses stored input values, while discovery and map analysis apply dataScale; preprocessing must be reconciled before model reuse. At least three independent groups per class are a code-level validation minimum, not sufficient field evidence. Group related windows by session or incident to avoid leakage. Hold out sites, seasons and incidents. Current output probabilities are uncalibrated, and the default 0.7 review threshold is not an approved operating point. The single-label model cannot describe simultaneous ice and galloping.

SOURCE / docs/event-ml.md · src/Capture/event_ml.py

## 12 — Software checks do not establish field performance

The documentation records 58 Python tests passed, a successful production frontend build, desktop/mobile browser checks with no page errors, save/reload/history checks, and three recordings published as archive replay on 16 September 2026. These checks were not rerun for this presentation and do not establish a live field deployment. Asset migrations 001–003 were previously applied to the server. Investigation migration 004 is in the local clone only; production deployment is not included.

SOURCES / docs/map-app.md · docs/event-ml.md · docs/masts.md · recorded pilot results

## 13 — Advance through evidence gates, then expand deployment

This is a proposed execution sequence, not an approved schedule. Workstreams can overlap when dependencies are satisfied. Ice-related validation depends on observing representative conditions, so calendar promises would be premature. Agree accountable owners and gate criteria before execution. Phase 1 includes resolving legacy mapping conflicts and an explicit preprocessing contract; phase 2 adds humidity and source-validity timestamps; phase 3 validates on independent incidents; phase 4 begins in shadow mode with human review.

PROPOSAL / grounded in the documented project limitations and deployment prerequisites

## 14 — Measure detection quality and operational usefulness

Report performance by class and condition with sample counts and uncertainty. Evaluate at incident level, not only window level. False alerts should be reported per monitored route-day or another agreed coverage unit. Acquisition-to-alert latency must distinguish acquisition time from publication and processing time. Location error requires verified physical events. Measure missing data and unavailable coverage. Pair technical results with review burden, useful findings and independently verified outcomes; avoided costs remain unproven.

PROPOSAL / validation plan; no performance results or target commitments implied

## 15 — Prepare the platform for controlled operations

Current local deployment uses loopback, a local database copy, same-origin write checks and self-reported reviewer names. Production requires authenticated identities, suitable authorization, a restricted database role, reviewed migration 004 and deliberate service enablement. Supervisor templates default autostart=false. Proposed reliability work includes retention planning, backup/restore tests, health monitoring and integration-specific alert delivery. Incident aggregation should preserve source file/sample/channel evidence, distinguish a candidate from a sustained incident and support review/closure.

SOURCES / docs/map-app.md deployment boundary · docs/event-ml.md next steps; extensions proposed

## 16 — Fund the next evidence milestone

No investment amount, commercial claim, customer commitment or staffing assignment is implied. Proposed decisions: select representative pilot routes and field access; assign data, domain-review and operations accountability; approve acceptance measures and production prerequisites. The concrete deliverable is a verified evidence pack plus held-out results and an operational acceptance decision. Data capture should include quiet normal operation, windy normal operation and independently verified target incidents. Seasonal or rare conditions may require a longer observation period.

PROPOSAL / scope, resources, target values and schedule to be agreed by Ubeconn AS

## 17 — Sources and scope behind the presentation

Source precedence: current implementation documentation and artifacts supersede older architecture descriptions in AGENTS.md. Specifically the capture pipeline now uses file-backed snapshots and the main application is FastAPI + React rather than the retired Dash contract. Snapshot counts are historical observations, not refreshed server queries. No database, application or production configuration was changed to create this presentation. Roadmap and acceptance slides are proposals.

COMPILED / 16 SEP 2026 · repository working tree and recorded project evidence

## 18 — A simple identity, grounded in ube purple

The logo is intentionally a plain lowercase white wordmark. The colours are a proposed Ubeconn palette inspired by ube flesh, not a standardized botanical colour reference. Background: deep plum #1D1429. Panel #2B1E3A. Primary ube #9D6BD0. Accent lavender #CFADF0. Text #F6F0FC. Plain logo #FFFFFF. IBM Plex Sans is body text, IBM Plex Sans Condensed bold is for headings, IBM Plex Mono is for labels. Fonts are supplied under the included SIL Open Font License. PowerPoint text remains editable; the PDF is a font-stable companion.

BRAND ASSETS / white vector wordmark + transparent PNG + IBM Plex fonts (OFL)