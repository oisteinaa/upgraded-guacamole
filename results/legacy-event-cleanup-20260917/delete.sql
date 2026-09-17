\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '10s';
WITH removed AS (
 DELETE FROM public.events
 WHERE id BETWEEN 1 AND 115847 AND classid IS NULL AND type = 1
 AND time BETWEEN TIMESTAMP '2025-04-22 23:10:22.360459' AND TIMESTAMP '2025-06-02 19:57:30.687395'
 RETURNING id
)
SELECT count(*) AS deleted_legacy_events FROM removed;
COMMIT;
BEGIN READ ONLY;
SELECT count(*) AS remaining_events FROM public.events;
SELECT * FROM public.event_classes ORDER BY classid;
COMMIT;
