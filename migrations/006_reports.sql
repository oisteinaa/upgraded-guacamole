-- Additive reporting workflow. Existing event metric/class identifiers are preserved.
BEGIN;
INSERT INTO event_classes(classid,name)
SELECT (SELECT coalesce(max(classid),0)+1 FROM event_classes), 'Structural / Attachment Anomaly'
WHERE NOT EXISTS (SELECT 1 FROM event_classes WHERE name='Structural / Attachment Anomaly');
INSERT INTO event_classes(classid,name)
SELECT (SELECT coalesce(max(classid),0)+1 FROM event_classes), 'Sensing / Acquisition Artefact'
WHERE NOT EXISTS (SELECT 1 FROM event_classes WHERE name='Sensing / Acquisition Artefact');
CREATE TABLE IF NOT EXISTS report_runs (
 id bigserial PRIMARY KEY, kind text NOT NULL CHECK(kind IN ('weekly','manual','historical')),
 period_start timestamptz NOT NULL, period_end timestamptz NOT NULL,
 rules_version text NOT NULL, status text NOT NULL DEFAULT 'running'
 CHECK(status IN ('running','published','failed')),
 created_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz,
 summary jsonb NOT NULL DEFAULT '{}', ai_status text NOT NULL DEFAULT 'pending',
 ai_analysis jsonb, ai_metadata jsonb NOT NULL DEFAULT '{}', error text,
 UNIQUE(kind,period_end,rules_version), CHECK(period_end>period_start)
);
CREATE TABLE IF NOT EXISTS report_findings (
 id bigserial PRIMARY KEY, mast_id integer NOT NULL REFERENCES masts(id),
 family text NOT NULL, status text NOT NULL DEFAULT 'open'
 CHECK(status IN ('open','investigating','closed')),
 priority text NOT NULL CHECK(priority IN ('red','yellow')),
 first_seen timestamptz NOT NULL, last_seen timestamptz NOT NULL,
 parent_id bigint REFERENCES report_findings(id), revision integer NOT NULL DEFAULT 0,
 classid smallint REFERENCES event_classes(classid), inconclusive boolean NOT NULL DEFAULT false,
 closed_at timestamptz, closure_reason text, closure_note text,
 closure_observation jsonb, verified boolean NOT NULL DEFAULT false,
 verification_evidence text, verified_by text, verified_at timestamptz,
 CHECK(NOT verified OR (classid IS NOT NULL AND NOT inconclusive AND length(trim(verification_evidence))>0 AND length(trim(verified_by))>0)),
 CHECK(status<>'closed' OR (closed_at IS NOT NULL AND length(trim(closure_reason))>0 AND length(trim(closure_note))>0 AND (classid IS NOT NULL OR inconclusive)))
);
CREATE UNIQUE INDEX IF NOT EXISTS report_findings_one_active ON report_findings(mast_id,family) WHERE status<>'closed';
CREATE TABLE IF NOT EXISTS report_observations (
 id bigserial PRIMARY KEY, report_id bigint NOT NULL REFERENCES report_runs(id),
 finding_id bigint NOT NULL REFERENCES report_findings(id),
 assessment text NOT NULL CHECK(assessment IN ('new','continuing','recurrence','not_flagged','unavailable','suppressed')),
 metrics jsonb NOT NULL, UNIQUE(report_id,finding_id)
);
CREATE TABLE IF NOT EXISTS report_evidence (
 id bigserial PRIMARY KEY, report_id bigint NOT NULL REFERENCES report_runs(id),
 mast_id integer NOT NULL REFERENCES masts(id), finding_id bigint REFERENCES report_findings(id),
 recording_id bigint REFERENCES das_recordings(id), source_epoch double precision NOT NULL,
 channel integer NOT NULL, configuration text NOT NULL, metadata jsonb NOT NULL,
 archive_path text, sha256 text, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(report_id,mast_id,recording_id,channel)
);
CREATE TABLE IF NOT EXISTS report_finding_reviews (
 id bigserial PRIMARY KEY, finding_id bigint NOT NULL REFERENCES report_findings(id),
 reviewer text NOT NULL CHECK(length(trim(reviewer))>0),
 action text NOT NULL, note text NOT NULL CHECK(length(trim(note))>0),
 before_state jsonb NOT NULL, after_state jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS report_event_links (
 finding_id bigint PRIMARY KEY REFERENCES report_findings(id), event_id integer NOT NULL REFERENCES events(id),
 evidence_id bigint REFERENCES report_evidence(id), reviewer text NOT NULL,
 note text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS report_observations_finding ON report_observations(finding_id,report_id DESC);
CREATE INDEX IF NOT EXISTS report_evidence_finding ON report_evidence(finding_id);
CREATE TABLE IF NOT EXISTS report_training_labels (
 evidence_id bigint PRIMARY KEY REFERENCES report_evidence(id),
 classid smallint NOT NULL REFERENCES event_classes(classid),
 reviewer text NOT NULL, verification_evidence text NOT NULL,
 verified_at timestamptz NOT NULL DEFAULT now(), active boolean NOT NULL DEFAULT true
);
COMMIT;
