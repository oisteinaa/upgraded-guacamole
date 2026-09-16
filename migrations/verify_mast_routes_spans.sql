-- Read-only content checks, followed by constraint tests that roll back.
\set ON_ERROR_STOP on
BEGIN READ ONLY;
SELECT r.route, r.name,
    (SELECT count(*) FROM public.masts m WHERE m.route=r.route) AS masts,
    (SELECT count(*) FROM public.mast_spans s WHERE s.route=r.route) AS spans
FROM public.mast_routes r ORDER BY r.route;
SELECT route, count(*) AS masts,
    round(percentile_cont(0.5) WITHIN GROUP (ORDER BY channel_distance_m)::numeric, 3) AS median_channel_distance_m,
    round(max(channel_distance_m)::numeric, 3) AS max_channel_distance_m
FROM public.masts GROUP BY route ORDER BY route;
SELECT route, from_mast, to_mast, round(straight_length_m::numeric, 1) AS length_m,
    water_status, installation FROM public.v_water_spans ORDER BY route, span_order;
SELECT route, mast, channel, round(channel_distance_m::numeric, 2) AS distance_m
FROM public.masts WHERE channel_distance_m > 10 ORDER BY route, route_position;
DO $$ BEGIN
    IF (SELECT count(*) FROM public.masts) <> 579
       OR (SELECT count(*) FROM public.v_mast_spans) <> 575
       OR (SELECT count(*) FROM public.v_water_spans) <> 7 THEN
        RAISE EXCEPTION 'Wrong imported counts';
    END IF;
    IF EXISTS (SELECT 1 FROM public.masts m LEFT JOIN public.masteliste c
        ON (c.channel, c.lid) = (m.channel, m.lid) WHERE c.id IS NULL) THEN
        RAISE EXCEPTION 'Unresolved nearest channel';
    END IF;
    IF EXISTS (SELECT 1 FROM public.masts WHERE route='R06'
        AND id <> 189-substring(mast FROM 2)::integer) THEN
        RAISE EXCEPTION 'Legacy R06 ID changed';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.v_mast_spans
        WHERE route='R14' AND from_mast='M38A' AND to_mast='M35') THEN
        RAISE EXCEPTION 'Incorrect R14 replacement mast order';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.v_mast_spans
        WHERE route='R13' AND from_mast='M37' AND to_mast='M39'
        AND review_reason IS NOT NULL) THEN
        RAISE EXCEPTION 'R13 missing-number connection not flagged';
    END IF;
    IF EXISTS (SELECT 1 FROM public.v_mast_spans
        WHERE crosses_water IS NOT NULL OR installation <> 'unknown') THEN
        RAISE EXCEPTION 'Inferred water/placement has been treated as confirmed';
    END IF;
END $$;
COMMIT;

BEGIN;
DO $$ BEGIN
    BEGIN
        UPDATE public.mast_spans SET to_mast_id =
            (SELECT id FROM public.masts WHERE route='R12' AND mast='M1')
        WHERE id=1;
        RAISE EXCEPTION 'Cross-route endpoint incorrectly accepted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        UPDATE public.mast_spans SET water_status='invalid' WHERE id=1;
        RAISE EXCEPTION 'Invalid water status incorrectly accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        UPDATE public.masts SET mast='M1' WHERE route='R12' AND mast='M2';
        RAISE EXCEPTION 'Duplicate mast within route incorrectly accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
END $$;
ROLLBACK;
