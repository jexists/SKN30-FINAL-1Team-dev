-- AgentRun을 FastAPI 프로세스 메모리가 아닌 PostgreSQL 영속 큐로 실행한다.
BEGIN;

ALTER TABLE public.agent_run
    ADD COLUMN IF NOT EXISTS report_id uuid REFERENCES public.report (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS request_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS request_hash text,
    ADD COLUMN IF NOT EXISTS error_code text,
    ADD COLUMN IF NOT EXISTS apply_status text NOT NULL DEFAULT 'not_applicable',
    ADD COLUMN IF NOT EXISTS current_stage_code text NOT NULL DEFAULT 'queued',
    ADD COLUMN IF NOT EXISTS attempt_count integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS base_report_version bigint,
    ADD COLUMN IF NOT EXISTS base_generation_input_version bigint,
    ADD COLUMN IF NOT EXISTS lease_owner text,
    ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz,
    ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz,
    ADD COLUMN IF NOT EXISTS next_attempt_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS input_tokens bigint,
    ADD COLUMN IF NOT EXISTS output_tokens bigint,
    ADD COLUMN IF NOT EXISTS total_tokens bigint,
    ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();

UPDATE public.agent_run
SET report_id = (source_refs ->> 'report_id')::uuid
WHERE report_id IS NULL
  AND source_refs ->> 'report_id'
      ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
  AND EXISTS (
      SELECT 1
      FROM public.report
      WHERE report.id = (agent_run.source_refs ->> 'report_id')::uuid
  );

UPDATE public.agent_run
SET created_at = coalesce(started_at, finished_at, created_at),
    current_stage_code = CASE status_code
        WHEN 'completed' THEN 'completed'
        WHEN 'failed' THEN 'failed'
        ELSE status_code
    END;

-- migration 전에 running이던 행은 구 FastAPI BackgroundTasks가 아직 실행 중일 수 있다.
-- lease를 임의 만료시키면 같은 LLM 요청이 중복 실행되므로 그대로 둔다. 새 API가 만든
-- request_hash가 있는 행만 범용 worker가 선점하고, 구 pipeline 행은 기존 직접 실행이 끝낸다.

UPDATE public.agent_run SET output_snapshot = NULL WHERE output_snapshot = 'null'::jsonb;
UPDATE public.agent_run SET evidence = NULL WHERE evidence = 'null'::jsonb;

UPDATE public.agent_run AS run
SET apply_status = CASE
    WHEN EXISTS (
        SELECT 1
        FROM public.report
        WHERE report.id = run.report_id
          AND report.source_snapshot ->> 'meeting_run_id' = run.id::text
    ) THEN 'applied'
    WHEN run.status_code IN ('queued', 'running', 'completed') THEN 'pending'
    ELSE 'not_applicable'
END
WHERE run.agent_code = 'meeting_processing';

ALTER TABLE public.agent_run
    DROP CONSTRAINT IF EXISTS agent_run_status_code_check;

ALTER TABLE public.agent_run
    ADD CONSTRAINT agent_run_status_code_allowed
        CHECK (status_code IN ('queued', 'running', 'completed', 'partial', 'failed', 'cancelled')),
    ADD CONSTRAINT agent_run_apply_status_allowed
        CHECK (apply_status IN ('pending', 'applied', 'stale', 'not_applicable')),
    ADD CONSTRAINT agent_run_request_snapshot_object
        CHECK (jsonb_typeof(request_snapshot) = 'object'),
    ADD CONSTRAINT agent_run_output_snapshot_object
        CHECK (output_snapshot IS NULL OR jsonb_typeof(output_snapshot) = 'object'),
    ADD CONSTRAINT agent_run_evidence_object
        CHECK (evidence IS NULL OR jsonb_typeof(evidence) = 'object'),
    ADD CONSTRAINT agent_run_request_hash_sha256
        CHECK (request_hash IS NULL OR request_hash ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT agent_run_attempt_count_range
        CHECK (attempt_count BETWEEN 0 AND 3),
    ADD CONSTRAINT agent_run_token_counts_nonnegative
        CHECK (
            (input_tokens IS NULL OR input_tokens >= 0)
            AND (output_tokens IS NULL OR output_tokens >= 0)
            AND (total_tokens IS NULL OR total_tokens >= 0)
        );

CREATE INDEX IF NOT EXISTS agent_run_queue_claim_idx
    ON public.agent_run (next_attempt_at, created_at)
    WHERE status_code = 'queued' AND request_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS agent_run_expired_lease_idx
    ON public.agent_run (lease_expires_at)
    WHERE status_code = 'running' AND request_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS agent_run_report_created_idx
    ON public.agent_run (report_id, created_at DESC)
    WHERE report_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS agent_run_meeting_active_report_key
    ON public.agent_run (report_id)
    WHERE agent_code = 'meeting_processing'
      AND status_code IN ('queued', 'running')
      AND request_hash IS NOT NULL;

COMMENT ON COLUMN public.agent_run.request_snapshot IS
    '클라이언트의 검증된 실행 요청. CRM 조회 전 먼저 저장하며 실제 모델 입력과 분리한다.';
COMMENT ON COLUMN public.agent_run.input_snapshot IS
    'worker가 실행 직전에 구성하고 이후 재시도에서도 재사용하는 고정 모델 입력.';
COMMENT ON COLUMN public.agent_run.lease_expires_at IS
    'worker가 죽었을 때 다른 worker가 실행을 회수할 수 있는 lease 만료 시각.';

COMMIT;
