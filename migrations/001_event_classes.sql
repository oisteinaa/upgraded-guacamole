-- Apply through psql with ON_ERROR_STOP enabled. Legacy events remain unclassified.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

CREATE TABLE IF NOT EXISTS public.event_classes (
    classid smallint PRIMARY KEY,
    name varchar(32) NOT NULL UNIQUE
);

INSERT INTO public.event_classes (classid, name) VALUES
    (1, 'Normal Operations'),
    (2, 'Ice Loading'),
    (3, 'Wind Galloping'),
    (4, 'External Interference')
ON CONFLICT (classid) DO NOTHING;

-- Refuse conflicting existing mappings rather than silently relabeling events.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM (VALUES
            (1, 'Normal Operations'), (2, 'Ice Loading'),
            (3, 'Wind Galloping'), (4, 'External Interference')
        ) AS expected(classid, name)
        LEFT JOIN public.event_classes c USING (classid)
        WHERE c.name IS DISTINCT FROM expected.name
    ) THEN
        RAISE EXCEPTION 'Existing event class IDs do not match the expected mapping';
    END IF;
END $$;

ALTER TABLE public.events ADD COLUMN IF NOT EXISTS classid smallint;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.events'::regclass
          AND conname = 'events_classid_fkey'
    ) THEN
        ALTER TABLE public.events ADD CONSTRAINT events_classid_fkey
            FOREIGN KEY (classid) REFERENCES public.event_classes (classid);
    END IF;
END $$;

COMMENT ON COLUMN public.events.classid IS
    'Optional event classification. NULL means unclassified, including legacy alarms; not Normal Operations.';
COMMENT ON TABLE public.event_classes IS
    'Event classes: 1 Normal Operations, 2 Ice Loading, 3 Wind Galloping, 4 External Interference. Separate from event_data_types metrics.';
COMMIT;
