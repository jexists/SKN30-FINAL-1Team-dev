-- 캘린더 "AI 추천 일정" 패널이 매번 LLM을 다시 부르지 않고 조회만 하도록, 지금 이
-- 영업 건에 보여줄 제안이 있는지를 담는 얇은 상태 테이블을 만든다.
--
-- 실행 이력 자체(입력·출력·평가 근거)는 agent_run 이 이미 감사로그로 갖고 있다. 이 테이블은
-- "지금 캘린더에 뭘 보여줄지"라는 다른 개념만 담는다 — 계약에이전트_설계.md 6장
-- "제안 상태 저장" 참고. 날짜·시간·사유 같은 실제 내용은 여기 복제하지 않고
-- schedule_management_run_id 로 agent_run.output_snapshot 을 그대로 조회한다.
--
-- 영업 건 하나에 활성 제안은 최대 1개다(sales_deal_id UNIQUE). 트리거(보고서 확정·일정
-- 수동 등록·영업 딜 생성/이동·CS 처리 시작, 계약에이전트_설계.md 3장)가 같은 딜에 대해
-- 다시 발생하면 기존 행을 새 실행으로 덮어쓰고 status_code 를 pending 으로 되돌린다.
-- 사용자가 닫은(dismissed) 제안도 그 딜에 새 변화가 생기면 다시 올라온다는 뜻이다.

-- 개발 DB 에는 이 표가 이미 있다. 아카이브한 브랜치
-- (archive/2026-08-28-contract-agent-fix)를 시험하며 SQL 파일 없이 먼저 만들어 둔 것이라,
-- 그 환경에서도 그대로 실행할 수 있게 IF NOT EXISTS 로 둔다. 컬럼·제약은 그 표와 같다.

BEGIN;

CREATE TABLE IF NOT EXISTS public.contract_next_meeting_suggestion (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    sales_deal_id uuid NOT NULL REFERENCES public.sales_deal (id),
    schedule_management_run_id uuid NOT NULL REFERENCES public.agent_run (id),
    status_code text NOT NULL
        CHECK (status_code IN ('pending', 'dismissed', 'accepted')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (sales_deal_id)
);

COMMENT ON TABLE public.contract_next_meeting_suggestion IS
    '캘린더 AI 추천 일정 패널이 조회하는 제안 상태. 내용은 agent_run 에 있다.';

-- 패널 조회는 팀 안에서 pending 만 훑는다.
CREATE INDEX IF NOT EXISTS contract_next_meeting_suggestion_team_status_idx
    ON public.contract_next_meeting_suggestion (team_id, status_code);

ALTER TABLE public.contract_next_meeting_suggestion ENABLE ROW LEVEL SECURITY;

COMMIT;
