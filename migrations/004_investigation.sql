-- Additive: existing event writers and identifiers retain their meaning.
BEGIN;
CREATE TABLE IF NOT EXISTS public.das_recordings (
    id bigserial PRIMARY KEY,
    relative_path text UNIQUE NOT NULL,
    acquisition_epoch double precision NOT NULL,
    dt double precision NOT NULL CHECK (dt > 0),
    samples integer NOT NULL CHECK (samples > 0),
    channels integer[] NOT NULL,
    unit text NOT NULL,
    scale double precision NOT NULL,
    size_bytes bigint NOT NULL,
    mtime_ns bigint NOT NULL,
    lid integer,
    time_verified boolean NOT NULL DEFAULT false,
    mapping_verified boolean NOT NULL DEFAULT false,
    processing text NOT NULL DEFAULT 'stored values × dataScale',
    indexed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS public.event_context (
    event_id integer PRIMARY KEY REFERENCES public.events(id),
    recording_id bigint REFERENCES public.das_recordings(id),
    start_sample integer CHECK (start_sample >= 0),
    stop_sample integer,
    lid integer,
    channel integer,
    route varchar(16) REFERENCES public.mast_routes(route),
    alignment_verified boolean NOT NULL DEFAULT false,
    evidence text NOT NULL,
    FOREIGN KEY (channel, lid) REFERENCES public.masteliste(channel, lid),
    CHECK (stop_sample IS NULL OR stop_sample > start_sample),
    CHECK ((channel IS NULL) = (lid IS NULL)),
    CHECK (NOT alignment_verified OR
           (recording_id IS NOT NULL AND start_sample IS NOT NULL AND stop_sample IS NOT NULL
            AND channel IS NOT NULL AND length(trim(evidence)) > 0))
);
CREATE TABLE IF NOT EXISTS public.event_reviews (
    id bigserial PRIMARY KEY,
    event_id integer NOT NULL REFERENCES public.events(id),
    previous_classid smallint REFERENCES public.event_classes(classid),
    classid smallint REFERENCES public.event_classes(classid),
    reviewer varchar(100) NOT NULL CHECK (length(trim(reviewer)) > 0),
    note text NOT NULL,
    reviewed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS events_time_id_idx ON public.events(time DESC, id DESC);
CREATE INDEX IF NOT EXISTS events_class_time_idx ON public.events(classid, time DESC);
CREATE INDEX IF NOT EXISTS event_reviews_event_idx ON public.event_reviews(event_id, id DESC);
CREATE INDEX IF NOT EXISTS weather_obs_station_time_idx ON public.weather_obs(lid, time);
CREATE INDEX IF NOT EXISTS das_recordings_acquisition_idx ON public.das_recordings(acquisition_epoch);
COMMIT;
