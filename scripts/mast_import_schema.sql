-- Template for scripts/prepare_mast_import.py. Apply the generated migration,
-- not this file. Once-only migration; all schema/data changes are transactional.
BEGIN;
SET LOCAL lock_timeout = '10s';
LOCK TABLE public.masts IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.masteliste IN SHARE MODE;
CREATE TEMP TABLE _original_masts (LIKE public.masts) ON COMMIT DROP;
-- INSERT_ORIGINAL_SNAPSHOT
DO $$ BEGIN
    IF EXISTS (SELECT * FROM public.masts EXCEPT SELECT * FROM _original_masts)
       OR EXISTS (SELECT * FROM _original_masts EXCEPT SELECT * FROM public.masts) THEN
        RAISE EXCEPTION 'Masts changed after snapshot; rebuild and review import';
    END IF;
END $$;
CREATE TEMP TABLE _expected_channels (
    lid integer, channel integer, latitude double precision, longitude double precision
) ON COMMIT DROP;
-- INSERT_CHANNEL_SNAPSHOT
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM _expected_channels e
        LEFT JOIN public.masteliste c USING (lid, channel)
        WHERE c.id IS NULL OR c.latitude IS DISTINCT FROM e.latitude
            OR c.longitude IS DISTINCT FROM e.longitude
    ) THEN RAISE EXCEPTION 'Matched channel coordinates changed; rebuild import'; END IF;
END $$;

CREATE TABLE public.mast_routes (
    route varchar(3) PRIMARY KEY,
    name text NOT NULL
);
INSERT INTO public.mast_routes VALUES
    ('R06', 'Fygle-Solbjørn'), ('R12', 'Svolvær-Kleppstad'),
    ('R13', 'Kvitfossen-Svolvær'), ('R14', 'Kleppstad-Fygle over Valberg');
ALTER TABLE public.masts
    DROP CONSTRAINT masts_lid_mast_key,
    ADD COLUMN route varchar(3) REFERENCES public.mast_routes(route),
    ADD COLUMN object_number bigint,
    ADD COLUMN route_position integer CHECK (route_position > 0),
    ADD COLUMN source_sheet text,
    ADD COLUMN source_row integer,
    ADD COLUMN source_sha256 varchar(64),
    ADD COLUMN mast_type text,
    ADD COLUMN voltage_kv double precision,
    ADD COLUMN owner text,
    ADD COLUMN mapped_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE public.masts ALTER COLUMN source_file DROP DEFAULT;
CREATE TEMP TABLE _mast_import (LIKE public.masts INCLUDING DEFAULTS) ON COMMIT DROP;
-- INSERT_MAST_ROWS

UPDATE public.masts m SET
    route = i.route, object_number = i.object_number, route_position = i.route_position,
    utmx = i.utmx, utmy = i.utmy, latitude = i.latitude, longitude = i.longitude,
    lid = i.lid, channel = i.channel, channel_distance_m = i.channel_distance_m,
    source_file = i.source_file, source_sheet = i.source_sheet, source_row = i.source_row,
    source_sha256 = i.source_sha256, mast_type = i.mast_type,
    voltage_kv = i.voltage_kv, owner = i.owner, mapped_at = CURRENT_TIMESTAMP
FROM _mast_import i WHERE m.id = i.id;
INSERT INTO public.masts (
    id, mast, route, object_number, route_position, utmx, utmy, latitude, longitude,
    lid, channel, channel_distance_m, source_file, source_sheet, source_row,
    source_sha256, mast_type, voltage_kv, owner
)
SELECT id, mast, route, object_number, route_position, utmx, utmy, latitude, longitude,
    lid, channel, channel_distance_m, source_file, source_sheet, source_row,
    source_sha256, mast_type, voltage_kv, owner
FROM _mast_import i WHERE NOT EXISTS (SELECT 1 FROM public.masts m WHERE m.id = i.id);
ALTER TABLE public.masts
    ALTER COLUMN route SET NOT NULL,
    ALTER COLUMN route_position SET NOT NULL,
    ADD CONSTRAINT masts_route_mast_key UNIQUE (route, mast),
    ADD CONSTRAINT masts_route_position_key UNIQUE (route, route_position),
    ADD CONSTRAINT masts_route_id_key UNIQUE (route, id),
    ADD CONSTRAINT masts_object_number_key UNIQUE (object_number);
COMMENT ON COLUMN public.masts.route IS 'Power-line route identity; lid remains DAS line identity and gid remains channel grouping.';
COMMENT ON COLUMN public.masts.route_position IS 'Imported connection order. R14 follows descending mapped channel, validated geographically; other routes follow mast numbers. Connections remain inferred.';
COMMENT ON COLUMN public.masts.source_sha256 IS 'SHA-256 of the source workbook used for this mapping.';
COMMENT ON COLUMN public.masts.mapped_at IS 'Time of latest coordinate/channel import. imported_at retains original mast insert time.';

CREATE TABLE public.mast_spans (
    id integer PRIMARY KEY,
    route varchar(3) NOT NULL REFERENCES public.mast_routes(route),
    span_order integer NOT NULL CHECK (span_order > 0),
    from_mast_id integer NOT NULL,
    to_mast_id integer NOT NULL,
    straight_length_m double precision NOT NULL CHECK (straight_length_m > 0),
    connection_basis text NOT NULL,
    connection_status text NOT NULL DEFAULT 'inferred'
        CHECK (connection_status IN ('inferred', 'confirmed')),
    review_reason text,
    water_status text NOT NULL DEFAULT 'unknown'
        CHECK (water_status IN ('unknown', 'map_candidate', 'confirmed_water', 'confirmed_land')),
    water_source text,
    installation text NOT NULL DEFAULT 'unknown'
        CHECK (installation IN ('unknown', 'overhead', 'submerged', 'underground', 'mixed')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (from_mast_id <> to_mast_id),
    UNIQUE (route, span_order),
    UNIQUE (route, from_mast_id, to_mast_id),
    FOREIGN KEY (route, from_mast_id) REFERENCES public.masts(route, id),
    FOREIGN KEY (route, to_mast_id) REFERENCES public.masts(route, id)
);
-- INSERT_SPAN_ROWS
CREATE INDEX mast_spans_from_idx ON public.mast_spans(from_mast_id);
CREATE INDEX mast_spans_to_idx ON public.mast_spans(to_mast_id);
COMMENT ON TABLE public.mast_spans IS 'Inferred connections between successive supplied masts within each route; not a verified inventory of physical spans. No inferred links across route boundaries.';
COMMENT ON COLUMN public.mast_spans.straight_length_m IS 'WGS84 ellipsoidal distance between endpoints at import, not sagged cable length or actual underwater path.';
COMMENT ON COLUMN public.mast_spans.water_status IS 'map_candidate means a possible crossing from map screening. unknown is not confirmed land. Water screening is not exhaustive.';
COMMENT ON COLUMN public.mast_spans.installation IS 'Cable placement requires independent confirmation; crossing water does not establish submerged installation.';

CREATE VIEW public.v_mast_spans AS
SELECT s.id AS span_id, s.route, r.name AS route_name, s.span_order,
    a.id AS from_mast_id, a.mast AS from_mast, b.id AS to_mast_id, b.mast AS to_mast,
    a.latitude AS from_latitude, a.longitude AS from_longitude,
    b.latitude AS to_latitude, b.longitude AS to_longitude,
    a.lid AS from_lid, a.channel AS from_channel,
    b.lid AS to_lid, b.channel AS to_channel,
    a.channel_distance_m AS from_channel_distance_m,
    b.channel_distance_m AS to_channel_distance_m,
    s.straight_length_m, s.connection_basis, s.connection_status,
    s.review_reason, s.water_status, s.water_source, s.installation,
    CASE s.water_status WHEN 'confirmed_water' THEN true
        WHEN 'confirmed_land' THEN false ELSE NULL END AS crosses_water,
    jsonb_build_object('type', 'LineString', 'coordinates',
        jsonb_build_array(jsonb_build_array(a.longitude, a.latitude),
                          jsonb_build_array(b.longitude, b.latitude))) AS geometry_geojson
FROM public.mast_spans s
JOIN public.mast_routes r ON r.route = s.route
JOIN public.masts a ON a.id = s.from_mast_id
JOIN public.masts b ON b.id = s.to_mast_id;
COMMENT ON VIEW public.v_mast_spans IS 'Dashboard span endpoints and straight-line GeoJSON in WGS84. Geometry is illustrative, not actual cable path. Numeric channel bounds do not establish monitored continuity.';
CREATE VIEW public.v_water_spans AS
SELECT * FROM public.v_mast_spans WHERE water_status IN ('map_candidate', 'confirmed_water');

DO $$ BEGIN
    IF (SELECT count(*) FROM public.masts) <> 579
       OR (SELECT count(*) FROM public.mast_spans) <> 575
       OR (SELECT count(*) FROM public.v_water_spans) <> 7
       OR (SELECT count(*) FROM public.v_mast_spans) <> 575 THEN
        RAISE EXCEPTION 'Unexpected imported row counts';
    END IF;
    IF EXISTS (SELECT 1 FROM _original_masts o
        LEFT JOIN public.masts m ON m.id=o.id AND m.mast=o.mast AND m.route='R06'
        WHERE m.id IS NULL) THEN RAISE EXCEPTION 'Original R06 identity changed'; END IF;
    IF EXISTS (SELECT 1 FROM public.mast_spans s
        JOIN public.masts a ON a.id=s.from_mast_id
        JOIN public.masts b ON b.id=s.to_mast_id
        WHERE a.route_position + 1 <> b.route_position
           OR s.span_order <> a.route_position) THEN
        RAISE EXCEPTION 'Span does not connect consecutive route positions';
    END IF;
END $$;
COMMIT;
