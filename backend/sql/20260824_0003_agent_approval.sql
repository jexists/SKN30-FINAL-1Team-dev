-- 계약관리·일정관리 Agent 승인 이력.
--
-- agent_run 은 제안 생성까지만 기록한다. 사용자가 일정 후보를 승인해 실제 activity 와
-- 브리핑 report 를 반영하면, 무엇을 승인했고 무엇이 만들어졌는지는 이 테이블에 남긴다.
-- support_response 처럼 상태 전이가 없는 단순 append-only 자식 레코드다.

BEGIN;

CREATE TABLE public.agent_approval (
    id uuid PRIMARY KEY,
    agent_run_id uuid NOT NULL REFERENCES public.agent_run (id),
    team_id uuid NOT NULL REFERENCES public.team (id),
    requested_by_member_id uuid NOT NULL REFERENCES public.member (id),
    idempotency_key uuid NOT NULL,
    decision_snapshot jsonb NOT NULL,
    result_refs jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (requested_by_member_id, idempotency_key)
);

CREATE INDEX agent_approval_run_idx ON public.agent_approval (agent_run_id);

ALTER TABLE public.agent_approval ENABLE ROW LEVEL SECURITY;

COMMIT;
