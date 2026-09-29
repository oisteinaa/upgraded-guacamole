# Oistein 17 sept 2026
## Remember
 Agreed—we’ll keep AC RMS as the current vibration metric and leave baseline learning until the live interrogator and its historical data
  are available.

  Then we can check acquisition timestamps, channel mapping and signal scaling, and identify representative normal periods for learning.
  Historical data will be useful, but we should review it before treating it as normal operation.

# Oistein 16 sept 2026
## Overview of the tech stack
The project has evolved from a collection of Flask/Dash pages into Cable Observatory: a React browser application backed by a Python
  API, PostgreSQL, and HDF5 recordings. Python still handles data processing, weather collection, and machine learning; the browser
  interface now has its own codebase.

  This summary reflects the current repository and documented deployment status.

  How the system fits together

  flowchart TD
      A[DAS interrogator / recording archive] --> B[HDF5 files]
      B --> C[Python signal processing and capture]
      C --> D[FastAPI backend]
      E[PostgreSQL: events, geography, weather, reviews] <--> D
      F[MET / YR forecasts] --> G[Python weather collector]
      G --> E
      D <--> H[React dashboard: map, charts, event review]
      B --> I[Offline pattern discovery and ML training]

  The main application supports three connected activities:

  - Explore the network: view fibre channels, masts, routes and inferred spans, with signal amplitude displayed along the fibre.
  - Inspect recordings: select channels and time windows, examine waveforms, heatmaps, RMS, variance and frequency spectra, and replay
    recorded data.

  - Review events: filter historical alarms, inspect available context, assign a class and preserve the reviewer’s evidence and
    classification history.

  Raw recordings remain in files. PostgreSQL stores searchable information and references to those files. The Python backend reads the
  requested recording slices and returns results to the browser.

  Programming languages and technologies

   Language            Purpose                                                    Main technologies
  ━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Python              API, HDF5 reading, signal analysis, capture, weather       FastAPI, Uvicorn, h5py, NumPy, SciPy, scikit-learn
                       and ML
  ──────────────────  ─────────────────────────────────────────────────────────  ─────────────────────────────────────────────────────────
   TypeScript / TSX    Interactive dashboard and browser state                    React, MapLibre, Plotly
  ──────────────────  ─────────────────────────────────────────────────────────  ─────────────────────────────────────────────────────────
   CSS and HTML        Appearance and browser page structure                      Nord styling, IBM Plex fonts
  ──────────────────  ─────────────────────────────────────────────────────────  ─────────────────────────────────────────────────────────
   SQL                 Database tables, relationships, queries and migrations     PostgreSQL
  ──────────────────  ─────────────────────────────────────────────────────────  ─────────────────────────────────────────────────────────
   Bash                Starting services, copying the database and running        Scripts in scripts/
                       collectors
  ──────────────────  ─────────────────────────────────────────────────────────  ─────────────────────────────────────────────────────────
   JavaScript          Browser execution and frontend tests                       TypeScript compiles to JavaScript; Node runs build/test
                                                                                  tools

  JSON, CSV and HDF5 are data formats, rather than programming languages.

  What changed from Flask/Dash

  Previously, Python/Dash defined the interface and its callbacks. The new application separates responsibilities:

   Earlier design                                         Current implementation
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Multiple Dash pages and Python callbacks               One React application
  ─────────────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
   Flask-based application entry points                   FastAPI served by Uvicorn
  ─────────────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
   Python controls browser interactions                   TypeScript manages selections, playback and interface updates
  ─────────────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
   Older capture processing and data-serving contracts    Indexed HDF5 files, bounded reads and shared capture snapshots
  ─────────────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
   Threshold alarms with limited context                  Event review history and explicit recording references where verified

  Some old filenames remain. In particular, flask_app.py, map_plot.py and Capture/restserver.py now launch or expose the FastAPI
  application. Their names no longer describe their implementation.

  Other older Dash modules remain in the repository, but they are not the main application launched by run_map_local.sh.

  Where the code lives

  All paths below are relative to /home/venator/upgraded-guacamole.

   Directory                                Contents and responsibility
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   web/src                                  Current dashboard: main.tsx coordinates the application; Map.tsx draws the map;
                                            SignalPanel.tsx and Chart.tsx provide signal inspection; style.css defines appearance.
  ───────────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   src/Mapui                                Current backend alongside retained legacy UI modules. api.py defines HTTP endpoints, db.py
                                            connects to PostgreSQL, signals.py reads recordings, metrics.py calculates map metrics, and
                                            live.py manages capture snapshots.
  ───────────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   src/Capture                              Capture/replay, threshold detection, offline pattern discovery and supervised ML. Includes
                                            both current and older capture scripts.
  ───────────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   src/weather                              MET/YR forecast collector.
  ───────────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   src/sensnetlib/                          Older shared database helpers.
  ───────────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   src/cron_jobs/, src/interrogator_sim/    Legacy scheduled processing and an interrogator simulator.
  ───────────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   migrations                               SQL changes for event classes, masts, spans, investigation records and distributed weather,
                                            plus verification scripts.
  ───────────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   scripts                                  Local startup, database cloning, recording indexing, mast import preparation and browser
                                            checks.
  ───────────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   tests, web/tests/                        Python and frontend tests.
  ───────────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   docs                                     Detailed implementation and operating documentation.
  ───────────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   results/                                 Mast import audit files and offline discovery outputs.
  ───────────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   presentations/                           Generated presentations, build scripts and speaker notes.
  ───────────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   supervisord/                             Service configuration templates for deployment.

  Where data and installed dependencies live

  The hidden .local/ directory holds the prepared local working environment:

  .local/
  ├── recordings/       Copied HDF5 recordings
  ├── pgdata/           Local PostgreSQL database files
  ├── pgsocket/         Local database connection socket
  ├── sensnetdb.dump     Source database snapshot
  ├── metric-cache/     Cached recording metrics
  ├── weather-cache/    Cached forecast responses
  ├── live.json         Latest capture/replay snapshot
  ├── runtime/          Local PostgreSQL and Node binaries
  ├── browsers/         Browser testing installation
  └── screenshots/      Verification screenshots

  Additional generated directories are:

  - .venv-map/: installed Python environment and dependencies.
  - web/node_modules/: frontend build dependencies.
  - web/dist/: compiled browser application served by FastAPI.

  These runtime directories, copied recordings and frontend build output are excluded from Git. A Git checkout alone therefore does not
  include the local database or recording archive.

  PostgreSQL stores weather, channel coordinates, masts, routes, spans and events. The local investigation additions also store recording
  metadata, event-to-recording context and review history. The large raw signal arrays stay in HDF5.

  Detection, machine learning and current status

  Signal colors and threshold crossings show measured activity; they do not automatically establish ice loading or galloping.

  Two offline Python workflows support developing that capability:

  - event_discovery.py groups similar signal windows and ranks unusual examples for human review.
  - event_ml.py trains a supervised classifier for Normal Operations, Ice Loading, Wind Galloping and External Interference using verified
    labels.

  The repository supplies the workflows, but does not supply a field-validated trained classifier. Historical unclassified events remain
  unclassified until reviewed.

  The new investigation dashboard is documented as a local installation. Separately, the distributed weather update has been applied to
  both the server and local database: 17 forecast locations collect temperature, wind speed, direction and relative humidity. Some older
  documentation still describes the earlier two-location setup.


# Oistein 15 septh 2026
## What the pilot found

  We can process the archive efficiently and distinguish signal patterns, but we have not identified confirmed cable events.

  - Coverage: 15 minutes of recordings, sampled across 16 channel blocks, produced 240 analyzed windows.
  - Grouping: The algorithm divided these into six clusters. Six was the configured maximum—not evidence of six physical event types.
  - Strong location differences: Three channel blocks stayed in the same high-amplitude, higher-frequency cluster throughout all 15
    minutes. This suggests the model is partly learning persistent differences between cable sections.

  - Interesting review targets:
      - Channels 6656–6780: changing patterns with prominent peaks around 3.65 and 5.1 Hz in several windows.
      - Channels 0–124: several highly ranked unusual windows, including peaks near 100 Hz. Their amplitudes were relatively low, showing
        that “unusual” does not necessarily mean strong vibration.

  - Practical result: Processing used about 160 MiB of memory. Rerunning reused all extracted features and reproduced identical results.

  These findings come from the review results (results/das-discovery-pilot-20260916/review.csv). No ice, galloping or vegetation strike is
  confirmed, and weather was not joined because timestamp alignment remains unverified.

  ## Basic next steps

  1. Inspect the interesting windows visually. Plot signal traces and frequency spectra for the two channel ranges above, alongside
     typical examples.

  2. Verify time and channel mapping. Confirm acquisition timestamps and identify which channels correspond to monitored cable sections.
  3. Expand to days or weeks with contrasting weather. Include calm, windy, cold and warmer periods, then match the appropriate weather
     station.

  4. Learn a baseline for each section. Detect changes relative to that section’s usual behavior, so permanently different sections do not
     dominate anomaly rankings.

  5. Add mast positions and verified labels. Analyze individual spans, compare measured frequency patterns, and label confirmed incidents
     before training an event classifier.

  My recommended next step is visual inspection of channels 6656–6780 and 0–124, followed by a longer weather-linked run.