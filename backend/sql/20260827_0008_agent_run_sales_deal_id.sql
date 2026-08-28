-- agent_run 이 어느 영업 건(딜)에 관한 실행인지를 컬럼으로 승격한다.
--
-- 지금까지는 report_id/activity_id/customer_company_id 처럼 agent_code 마다 다른 값이
-- source_refs(JSONB) 안에만 있어서, "이 딜의 히스토리 전체"를 인덱스로 조회할 방법이
-- 없었다. sales_deal_id 를 컬럼으로 두면 GET /agent-runs?sales_deal_id= 조회가 인덱스를
-- 탄다.
--
-- 딜 하나로 좁혀지지 않는 실행은 NULL 을 허용한다:
--   - contract_management_select_candidates: 담당자 포트폴리오 전체를 도는 실행
--   - contract_management_next_meeting: 회사(customer_company) 단위 실행
-- 이 두 agent_code 는 원래 "이 딜 하나"라는 개념이 없으므로 NOT NULL 로 만들지 않는다.
--
-- 기존 행은 백필하지 않는다. source_refs 안에 있던 report_id/activity_id 로 역추적할
-- 수는 있지만, 개발 DB 데모 데이터라 정합성을 보장하는 별도 백필 스크립트를 만들
-- 만큼의 가치가 없다고 판단했다 — 필요해지면 그때 채운다.

BEGIN;

ALTER TABLE public.agent_run
    ADD COLUMN sales_deal_id uuid REFERENCES public.sales_deal (id);

COMMENT ON COLUMN public.agent_run.sales_deal_id IS
    '이 실행이 어느 영업 건에 관한 것인지. 딜 하나로 좁혀지지 않는 실행(0차 선별, 회사 단위
    다음 미팅 제안)은 NULL.';

-- 딜 기준 히스토리 조회(team_id 로 먼저 스코프 좁힌 뒤 최신순)를 위한 인덱스.
CREATE INDEX agent_run_sales_deal_id_idx
    ON public.agent_run (team_id, sales_deal_id, started_at DESC);

COMMIT;
