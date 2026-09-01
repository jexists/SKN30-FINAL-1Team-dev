-- 팀장 업무 관리 흐름(보고서 검토 · 팀원 목표 관리 · 지시사항 이행)을 위한 스키마 변경.
--
-- 보고서 검토는 스키마를 바꾸지 않는다. report 에 status_code 와 reviewed_by_member_id,
-- reviewed_at, note 가 이미 있고 이번에 API 만 붙는다.
--
-- 여기서 바꾸는 것은 두 가지다.
--   1) sales_target 이 거래처 없는 "팀원 한 달 목표" 를 담을 수 있게 한다.
--   2) notice_target 에 지시사항 이행 여부를 남긴다.

BEGIN;

-- 1) 팀원 단위 매출 목표
--
-- 지금까지 목표는 (담당자, 거래처, 월) 단위였는데, 팀 관리 화면이 다루는 것은 거래처를
-- 가리지 않는 "이 사람의 이번 달 목표" 하나다. 거래처 컬럼을 비울 수 있게 열어 두고
-- customer_company_id IS NULL 인 행 하나를 그 사람의 월 목표로 삼는다.
ALTER TABLE public.sales_target
    ALTER COLUMN customer_company_id DROP NOT NULL;

COMMENT ON COLUMN public.sales_target.customer_company_id IS
    '거래처별 목표면 그 거래처. NULL 이면 거래처를 가리지 않는 담당자의 그달 목표다.';

-- 기존 UNIQUE (owner_member_id, customer_company_id, target_month) 는 NULL 을 서로 다른
-- 값으로 보아 팀원 목표를 여러 줄 허용한다. 한 사람의 한 달 목표는 하나여야 하므로
-- NULL 행만 따로 묶는다.
CREATE UNIQUE INDEX sales_target_member_month_key
    ON public.sales_target (owner_member_id, target_month)
    WHERE customer_company_id IS NULL;

-- 거래처별로 흩어져 있던 기존 목표를 담당자·월 단위 한 줄로 합친다.
--
-- sales_target 을 읽는 곳은 dashboard._sales_target_card 의 SUM 하나뿐이라, 합계만
-- 보존되면 대시보드 숫자는 그대로다. 합친 뒤라야 팀 관리 화면이 고칠 대상이 한 줄로
-- 정해진다. 대상이 없으면(이미 비어 있으면) 아무 일도 하지 않는다.
INSERT INTO public.sales_target (id, owner_member_id, customer_company_id, target_month, target_amount)
SELECT gen_random_uuid(), owner_member_id, NULL, target_month, SUM(target_amount)
  FROM public.sales_target
 WHERE customer_company_id IS NOT NULL
 GROUP BY owner_member_id, target_month;

DELETE FROM public.sales_target
 WHERE customer_company_id IS NOT NULL;

-- 2) 지시사항 이행 여부
--
-- 수신자마다 따로 남긴다. 한 지시가 여러 명에게 가므로 notice 쪽에 둘 수 없다.
-- pending 은 아직 담당자가 손대지 않은 상태다.
ALTER TABLE public.notice_target
    ADD COLUMN status_code text NOT NULL DEFAULT 'pending'
        CHECK (status_code IN ('pending', 'done', 'not_done')),
    ADD COLUMN status_reason text,
    ADD COLUMN status_changed_at timestamptz,
    ADD COLUMN status_changed_by_member_id uuid REFERENCES public.member (id);

COMMENT ON COLUMN public.notice_target.status_code IS
    '이 수신자의 이행 여부. pending 은 미처리, done 은 이행, not_done 은 미이행이다.';
COMMENT ON COLUMN public.notice_target.status_reason IS
    '미이행 사유. not_done 일 때만 채운다.';
COMMENT ON COLUMN public.notice_target.status_changed_by_member_id IS
    '상태를 바꾼 사람. 본인만 바꾸므로 지금은 member_id 와 같지만, 기록으로 남긴다.';

COMMIT;
