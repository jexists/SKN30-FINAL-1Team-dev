BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE public.agent_run
    ADD COLUMN IF NOT EXISTS progress_snapshot jsonb;

COMMIT;
