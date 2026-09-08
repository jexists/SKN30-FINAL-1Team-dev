-- Durable model budget/journal; worker retries keep the same parent row.
ALTER TABLE public.agent_run
    ADD COLUMN IF NOT EXISTS delegation_state jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS delegation_key text;
CREATE UNIQUE INDEX IF NOT EXISTS agent_run_parent_delegation_key
    ON public.agent_run (parent_run_id, delegation_key)
    WHERE delegation_key IS NOT NULL;
