-- Transactional checks: all test rows are rolled back; no sequence IDs consumed.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SELECT * FROM public.event_classes ORDER BY classid;
SELECT count(*) AS total_events,
       count(*) FILTER (WHERE classid IS NULL) AS unclassified_events
FROM public.events;
DO $$
BEGIN
    INSERT INTO public.events (id, type, value, comment)
        VALUES (-2147483648, 1, 0, 'Migration legacy insert check');
    IF (SELECT classid IS NOT NULL FROM public.events WHERE id = -2147483648) THEN
        RAISE EXCEPTION 'Legacy insert must remain unclassified';
    END IF;
    UPDATE public.events SET classid = 3 WHERE id = -2147483648;
    BEGIN
        UPDATE public.events SET classid = -1 WHERE id = -2147483648;
        RAISE EXCEPTION 'Invalid class ID was accepted';
    EXCEPTION WHEN foreign_key_violation THEN
        NULL;
    END;
END $$;
ROLLBACK;
