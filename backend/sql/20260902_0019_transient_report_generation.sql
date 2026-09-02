-- 보고서 생성은 AgentRun 임시 초안으로 끝내고 사용자 확정 때만 Report를 만든다.
-- Blue/green 전환 중 구 backend/worker가 읽는 기존 컬럼·인덱스·테이블은 유지한다.
-- 파괴적 정리는 구 컨테이너가 모두 종료된 뒤 별도 migration으로 수행한다.
BEGIN;

ALTER TABLE public.agent_run
    ADD COLUMN IF NOT EXISTS scope_key text,
    ADD COLUMN IF NOT EXISTS payload_expires_at timestamptz,
    ADD COLUMN IF NOT EXISTS payload_redacted_at timestamptz;

CREATE UNIQUE INDEX agent_run_active_generation_scope_key
    ON public.agent_run (team_id, requested_by_member_id, scope_key)
    WHERE agent_code IN ('meeting_processing', 'report_writing')
      AND status_code IN ('queued', 'running')
      AND report_id IS NULL
      AND scope_key IS NOT NULL;

CREATE INDEX agent_run_payload_expiry_idx
    ON public.agent_run (payload_expires_at)
    WHERE payload_expires_at IS NOT NULL AND payload_redacted_at IS NULL;

ALTER TABLE public.report_submission
    ADD COLUMN IF NOT EXISTS agent_run_id uuid REFERENCES public.agent_run (id),
    ADD COLUMN IF NOT EXISTS idempotency_key uuid,
    ADD COLUMN IF NOT EXISTS request_hash text;

ALTER TABLE public.report_submission
    ADD CONSTRAINT report_submission_request_hash_sha256
        CHECK (request_hash IS NULL OR request_hash ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT report_submission_idempotency_pair
        CHECK (
            (idempotency_key IS NULL AND request_hash IS NULL)
            OR (idempotency_key IS NOT NULL AND request_hash IS NOT NULL)
        ),
    ADD CONSTRAINT report_submission_submitter_idempotency_key
        UNIQUE (submitted_by_member_id, idempotency_key);

-- 확정 provenance와 멱등 정보도 제출 snapshot과 함께 불변이다.
CREATE OR REPLACE FUNCTION public.guard_report_submission_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF ROW(
        NEW.id,
        NEW.report_id,
        NEW.revision_no,
        NEW.report_version,
        NEW.team_id,
        NEW.submitted_by_member_id,
        NEW.agent_run_id,
        NEW.idempotency_key,
        NEW.request_hash,
        NEW.snapshot,
        NEW.snapshot_sha256,
        NEW.submitted_at
    ) IS DISTINCT FROM ROW(
        OLD.id,
        OLD.report_id,
        OLD.revision_no,
        OLD.report_version,
        OLD.team_id,
        OLD.submitted_by_member_id,
        OLD.agent_run_id,
        OLD.idempotency_key,
        OLD.request_hash,
        OLD.snapshot,
        OLD.snapshot_sha256,
        OLD.submitted_at
    ) THEN
        RAISE EXCEPTION 'report submission snapshot is immutable';
    END IF;

    IF OLD.review_status <> 'pending'
       AND ROW(NEW.review_status, NEW.reviewed_by_member_id, NEW.reviewed_at, NEW.review_note)
           IS DISTINCT FROM
           ROW(OLD.review_status, OLD.reviewed_by_member_id, OLD.reviewed_at, OLD.review_note)
    THEN
        RAISE EXCEPTION 'report submission review is already final';
    END IF;
    RETURN NEW;
END
$$;

COMMENT ON COLUMN public.agent_run.scope_key IS
    '서버가 report kind와 activity/date/period로 계산한 화면 재진입 범위.';
COMMENT ON COLUMN public.agent_run.payload_expires_at IS
    '보고서 미확정 초안을 복구할 수 있는 마지막 시각.';
COMMENT ON COLUMN public.agent_run.payload_redacted_at IS
    '원문·CRM·AI 결과 payload를 제거한 시각.';
COMMENT ON COLUMN public.report_submission.agent_run_id IS
    '사람이 이 확정본을 작성할 때 참고한 선택적 AgentRun.';

COMMIT;
