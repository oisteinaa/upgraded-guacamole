# Weekly integrity reports

The Reports tab provides a report reader and an active/closed finding queue. The dedicated user timer runs every Monday at **04:00 UTC**. Weekly periods end at Monday 00:00 UTC and include seven days of observations, interpreted using a rolling 30-day context. A manual run ends at the latest completed UTC hour. The October 22 shortlist is imported as unverified historical screening, not as training truth.

## Operation

```bash
bash scripts/run_reports_server.sh              # current example; deduplicated per UTC hour
bash scripts/run_reports_server.sh --weekly     # previous completed reporting week
bash scripts/run_reports_server.sh --retry-ai 2 # interpret an existing numerical snapshot
systemctl --user status sensnet-reports.timer
journalctl --user -u sensnet-reports.service
```

Worker dependencies are isolated in `.venv-reports` using `requirements-reports.txt`; the web service retains `.venv-map`. `.local/map-server.env` is preserved. Put `OPENAI_API_KEY=…` and optionally `DAS_REPORT_AI_MODEL=…` in `.local/report-ai.env`, mode 600. Default model: `gpt-6-astra`. Never commit this file. The worker sends a bounded packet of calculated statistics, selected plots, finding history and relevant human notes to the Responses API with `store=false`; no tools or mutation capability are provided. Do not put unrelated sensitive information in investigation notes. API failure produces a numerical report explicitly marked AI unavailable. Prompt/input hashes, model, response ID and usage are retained. `--retry-ai` uses retained numerical evidence and updates the interpretation without recomputing measurements.

Reports live in `.local/reports/ID/`; exact raw source windows are saved as compressed NPZ files with channel IDs, scale, sample interval and spectra before the recording archive expires. The database retains SHA-256 checksums and source recording/configuration identity. Never delete report evidence with the rolling raw-archive retention job. The timer uses UTC, persistent catch-up, and a process lock; a database uniqueness key prevents duplicate weekly reports. Failed runs can resume their committed numerical snapshot. Only the report worker is scheduled; it does not restart capture or the web service.

## Reading the evidence

Red/yellow indicate investigation priority. Green means not flagged by this screen; grey means insufficient usable evidence. None is a structural safety assessment. DAS phase-rate response cannot by itself establish a loose mast, ice, galloping or attachment damage.

One ten-second file is sampled per twenty-minute bucket. Signal/weather comparisons use hourly medians, explicit file channel IDs and acquisition fingerprints, never row indices. Core ±16.5 m is compared with flanks 48–120 m away, excluding other mast neighbourhoods. Forecast records must have valid, issue and collection times no later than acquisition; they must be sufficiently fresh and geographically close. MET/YR values are model forecasts, not mast-mounted measurements. Each wind comparison needs at least eight calm and eight windy hourly observations across at least two dates per group. Thresholds and coverage limits are printed in the report. Different configurations are never pooled for screening or recurrence. The report explicitly accounts for expired or changed sources. This sparse sampling does not establish the absence of short vegetation strikes or other transient events.

## Human decisions

- Save notes or mark investigating while work is ongoing.
- Publish a classified event using one selected source window, or link an existing event. Publication is idempotent and does not close the finding. Acquisition channel identity is preserved in evidence; event geometry alignment remains unverified rather than forcing an acquisition ID into the geometry-grid foreign key.
- Close using a classification (including the two new anomaly/artefact classes) or Inconclusive, a closure reason and notes. Closed cases disappear from the active queue. The same pattern stays suppressed unless post-closure, configuration-compatible evidence meets recurrence criteria. Repaired cases require a qualifying return; other closures require a twofold matched-weather contrast increase with sufficient hours on two dates. A different pattern can become a separate finding.
- Training verification is a separate explicit action on selected preserved windows. It requires an independently supported conclusion, a reviewer and valid evidence checksums. Closing a case, AI text or a threshold alarm does not create training labels. Verification can be revoked, retaining the audit history.

The ZIP export contains verified windows and `manifest.csv`. It groups connected finding/recurrence episodes and shared original recordings/UTC recording days to prevent leakage. The offline random-forest loader accepts NPZ evidence, applies stored scaling, and rejects mixed acquisition configurations. Train separate models per configuration. At least two supported classes and three independent groups per class are required. No automatic training or activation occurs. More rigorous site/time holdouts are still required before operational use.

## Deployment and rollback

Local source tag: `pre-weekly-reports-20261023`. The running server differed from that Git revision, so the authoritative pre-change backup is `/home/inst/oistein/rollback-weekly-reports-20261023/`: application archive, service/environment, calm baselines and PostgreSQL custom-format dump with checksums. `pg_restore -l` verified the dump catalog.

For application rollback, stop/disable `sensnet-reports.timer`, stop a running report worker, restore application files from `application.tar.gz`, restore the backed-up observatory unit/settings if necessary, and restart only `sensnet-observatory.service`. The migration is additive and may remain while the old application runs. **Do not restore the entire database over current data as a routine rollback**: that would erase subsequent observations/reviews. A database restoration requires a separate reviewed recovery operation. Preserve `.local/reports` and the reporting tables to retain human decisions and evidence.

Migration `006_reports.sql` preserves existing metric IDs and class IDs and adds report tables plus two class names. It was tested in a separate database with stale revisions, repeated event publication, closure, exact-window verification/export, checksum corruption and revocation checks. Test writes never touched production event records.
