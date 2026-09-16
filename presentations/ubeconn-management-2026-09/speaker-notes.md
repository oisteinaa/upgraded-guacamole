## 01 — Moving forward with event classification

Prepared for executive management. This is a new, less technical presentation, not an update to the previous deck. It uses the supplied purple logo unchanged and a brighter ube palette. Company name remains Ubeconn AS in text; the supplied artwork is not respelled. Current evidence supports a local investigation platform, a completed discovery pilot and supervised training software. It does not establish a field-validated classifier. Weather migration 005 is deployed on the server and local installation and supersedes the older two-location/no-humidity snapshot.

PROJECT UPDATE / 16 SEPTEMBER 2026

## 02 — The building blocks for event classification are in place

Sources: docs/map-app.md; docs/masts.md; docs/weather.md; docs/event-ml.md. User clarification: existing event entries were randomly generated demonstration data, not a historical incident archive or candidate training set. They are intended for future deletion; this presentation task does not delete database records. The local application supports investigation and review. The asset import contains 579 masts across four routes and 575 inferred links. Weather collection is deployed. Training code exists; a field-validated classifier still requires confirmed examples and testing.

EVIDENCE / project documentation; detailed sources and status in speaker notes

## 03 — A clear workflow for reviewing real recordings

Source: docs/map-app.md. The application supports asset search, signal inspection, archive replay and classification reviews with evidence notes and history. The prior screenshot was removed because it displayed randomly generated demonstration events. No demonstration event counts are presented as operational evidence. Classifying real recordings requires explicit verified time and location references. This workflow diagram describes capabilities, not a claim of production rollout.

WORKFLOW / based on the implemented local investigation application

## 04 — The new UI brings map, signals and review together

Sources: docs/map-app.md and assets/application-overview.png. Screenshot is an unchanged capture of the local application. Event entries and counts visible in the screen are randomly generated demonstration data, as clarified by the user; they are not real incidents, a training set or performance evidence. The slide illustrates interface capabilities only. The map displays assets and signal layers; the recording browser supports waveform, heatmap, spectrum and playback. The review panel supports a category, reviewer, evidence note and review history when an event is selected. No event is selected in this overview screenshot. The displayed recording is an independent archive example. Screenshot retains the original app branding and colours, and basemap attribution: OpenFreeMap / OpenMapTiles / OpenStreetMap. The supplied Ubeconn logo and pale ube slide palette remain unchanged.

SCREENSHOT / local application; demonstration entries shown for interface illustration only

## 05 — Weather context now follows more of the network

Migration 005_distributed_weather.sql and the collector were deployed on 16 September 2026. Two original locations remain; fifteen new points use mast coordinates across R06, R12, R13 and R14 at approximately five kilometre spacing. There are now 17 locations × four weather variables. Both installations recorded successful initial captures of 68 rows. Server capture runs hourly at minute 13; local capture is on demand. These are MET/YR modeled forecasts, not direct measurements. Source validity, issue and retrieval timestamps are stored on new rows. Integration with ML requires verified recording times, appropriate location selection and weather available at the time of the event.

EVIDENCE / docs/weather.md · migration 005 applied on server and local installation

## 06 — We use Random Forest machine learning for classification

Source: src/Capture/event_ml.py and docs/event-ml.md. The supervised baseline is a Random Forest with 300 decision trees and balanced class weights. Training uses signal summaries covering vibration strength, peaks, rhythmic behaviour, variability across channels and changes over the window, plus optional temperature, wind speed/direction and humidity. Missing weather is explicit. The model learns rules from reviewed examples; a new window receives a predicted class, four uncalibrated scores and a low-score review flag. No supervised trained model or measured field accuracy is supplied. The scores must not be presented as a validated confidence percentage. Weather must be aligned before being used. The baseline outputs a single category for each window, not an incident duration or severity.

MODEL STATUS / supervised training software implemented; field accuracy not yet established

## 07 — Two machine-learning steps support event classification

The offline discovery workflow uses clustering (KMeans) and anomaly ranking (Isolation Forest), without verified class labels. The recorded pilot covered roughly 15 minutes across 90 archive files, producing 240 window/block feature rows and six exploratory clusters. These clusters are not the four event classes. No weather join was used in that pilot. Human reviewers must use independent evidence, including inspections, cameras or confirmed incident records, to assign labels. A separate supervised Random Forest can then train on those examples. Related windows from one session/incident must stay in the same evaluation group, with additional unseen sites/seasons/incidents reserved for final assessment. Neither the pilot nor its six clusters demonstrates event-classification accuracy.

EVIDENCE / docs/event-discovery.md · recorded discovery pilot · docs/event-ml.md

## 08 — The goal is to distinguish four types of operation

Source: docs/event-ml.md; project objectives in AGENTS.md. Exact database class names are Normal Operations, Ice Loading, Wind Galloping and External Interference. Vegetation contact or strikes are examples for the External Interference category, not an independently validated vegetation classifier. Normal examples must include quiet and windy operation. Ice detection may need additional evidence, sensors or features; existing vibration features alone may not distinguish it reliably. The current model chooses one class per window and cannot express simultaneous ice and galloping. Class names do not establish severity, ice mass or loading force.

TARGET CATEGORIES / classification design; detection performance still to be validated

## 09 — Collect confirmed examples of real cable behaviour

Sources: user clarification; docs/event-ml.md; docs/map-app.md. Existing event records are randomly generated demonstration data and are excluded from the classification dataset. The user intends to delete them later; no database deletion is performed in this task. Collect verified real recordings for all four target classes, including varied normal operation. Retain recording/time/location references and independent evidence for every label. Keep related windows from the same incident grouped when evaluating the model. No amount of synthetic demonstration events establishes field performance.

NEXT PHASE / real recordings, expert labels and independent evaluation

## 10 — Start with verified examples, then classify with oversight

Proposed sequence grounded in docs/event-ml.md, docs/map-app.md and docs/weather.md. 1: select a manageable pilot scope and verify recording time, channel/location mapping, preprocessing and weather availability. 2: field experts label representative examples for all four classes, keeping independent incidents grouped and retaining evidence. 3: train the Random Forest and assess on independent events, measuring per-class precision/recall, false alerts, missed events and practical reviewer workload; confidence scores and thresholds need validation. 4: run class suggestions in a controlled pilot with human review before automating operational escalation. Model output is not yet integrated as a proven production classifier. No budget, schedule, numerical performance or customer commitment is implied. Initial management action: name a field-review owner and agree the pilot scope.

PROPOSED NEXT STEPS / scope, owners and acceptance targets to be agreed