-- 일정에 고객사(customer_company_id)를 둔다. 그 전에 대표 담당자가 빈 딜·일정을 정리한다.
--
-- 딜과 일정의 customer_contact_id 는 "이 회사에서 주로 연락하는 사람" 한 명이다. 비어 있으면
-- 계약관리 에이전트가 다음 미팅을 추천할 때 일정에 넣을 사람을 못 정하고, 그 일정은 AI 브리핑이
-- 아예 만들어지지 않는다. 목업 데이터에 빈 행이 남아 있어 여기서 한 번 정리한다.
--
-- 채울 수 있는 것과 없는 것이 갈린다.
--   * 고객사에 연락처가 있는 딜은 그 사람을 연결하면 끝난다. 일정은 붙어 있는 딜을 따라간다.
--   * 고객사에 연락처가 0명인 딜(seed_demo_contract_schedule.py 가 만든 DEMO-SEED-002~010)과,
--     딜도 고객사도 없는 '[지시] …' 할일 일정은 연결할 사람 자체가 없어 지운다.
--     '[지시]' 일정에 물린 보고서는 원본이 사라지면 근거를 잃으므로 함께 지운다.
--   * deleted_at 이 찍힌 행도 같이 다룬다. NOT NULL 은 소프트 삭제와 무관하게 전체 행에 걸린다.
--
-- 정리가 끝나면 activity.customer_contact_id 에 NULL 이 남지 않으므로, 담당자가 속한 회사를
-- customer_company_id 로 백필하고 NOT NULL 을 걸 수 있다. customer_contact_id 자체의 필수화는
-- 이 파일에서 하지 않는다(#110).
--
-- **DB 적용이 백엔드 배포보다 먼저다.** 새 코드는 조회에서 customer_company_id 를 읽으므로
-- 컬럼이 없으면 일정 조회가 통째로 깨진다. 반대로 이전 코드는 INSERT 에 이 값을 넣지 않아,
-- DB 를 적용한 뒤 배포 전까지는 일정 등록이 NOT NULL 에 막힌다. 두 작업을 붙여서 한다.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. 딜의 대표 담당자 백필
--
-- 고객사에 연락처가 여럿이면 직함이 있는 사람을 먼저 고르고, 그중 가장 먼저 등록된 사람을 쓴다.
-- 직함 없는 행은 명함·입력 테스트로 만들어진 이름뿐인 데이터라 뒤로 민다.
-- ---------------------------------------------------------------------------

WITH picked AS (
    SELECT DISTINCT ON (d.id)
        d.id AS deal_id,
        k.id AS contact_id
    FROM public.sales_deal d
    JOIN public.customer_contact k ON k.company_id = d.customer_company_id
    WHERE d.customer_contact_id IS NULL
    ORDER BY d.id, (k.job_title IS NULL), k.registered_at, k.id
)
UPDATE public.sales_deal d
    SET customer_contact_id = picked.contact_id
    FROM picked
    WHERE d.id = picked.deal_id;

-- ---------------------------------------------------------------------------
-- 2. 일정의 대표 담당자 백필
--
-- 딜에 붙은 일정은 그 딜의 담당자를 그대로 따른다. 1번에서 채운 딜도 여기에 들어온다.
-- ---------------------------------------------------------------------------

UPDATE public.activity a
    SET customer_contact_id = d.customer_contact_id
    FROM public.sales_deal d
    WHERE a.sales_deal_id = d.id
      AND a.customer_contact_id IS NULL
      AND d.customer_contact_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3. 채울 근거가 없는 행 삭제
--
-- 위 두 단계를 지나고도 담당자가 비어 있으면 연결할 사람이 없다는 뜻이다.
-- ---------------------------------------------------------------------------

CREATE TEMP TABLE dropped_deal ON COMMIT DROP AS
SELECT id FROM public.sales_deal WHERE customer_contact_id IS NULL;

CREATE TEMP TABLE dropped_activity ON COMMIT DROP AS
SELECT id FROM public.activity WHERE customer_contact_id IS NULL;

CREATE TEMP TABLE dropped_report ON COMMIT DROP AS
SELECT id FROM public.report
    WHERE source_activity_id IN (SELECT id FROM dropped_activity);

DO $$
DECLARE
    stuck integer;
BEGIN
    RAISE NOTICE '삭제 대상: 딜 % / 일정 % / 보고서 %',
        (SELECT count(*) FROM dropped_deal),
        (SELECT count(*) FROM dropped_activity),
        (SELECT count(*) FROM dropped_report);

    -- 지우는 딜에 자료·보고서·발주·불만이 걸려 있으면 조용히 지우지 않고 멈춘다.
    -- 확인한 개발 DB 에서는 전부 0건이며, 다른 환경에서 0이 아니면 사람이 판단해야 한다.
    SELECT
        (SELECT count(*) FROM public.document WHERE sales_deal_id IN (SELECT id FROM dropped_deal))
      + (SELECT count(*) FROM public.report_deal WHERE sales_deal_id IN (SELECT id FROM dropped_deal))
      + (SELECT count(*) FROM public.report WHERE sales_deal_id IN (SELECT id FROM dropped_deal))
      + (SELECT count(*) FROM public.purchase_order WHERE sales_deal_id IN (SELECT id FROM dropped_deal))
      + (SELECT count(*) FROM public.support_request WHERE sales_deal_id IN (SELECT id FROM dropped_deal))
      + (SELECT count(*) FROM public.sales_deal_item WHERE sales_deal_id IN (SELECT id FROM dropped_deal))
      + (SELECT count(*) FROM public.sales_deal_participant WHERE sales_deal_id IN (SELECT id FROM dropped_deal))
    INTO stuck;
    IF stuck <> 0 THEN
        RAISE EXCEPTION
            'activity_customer_company: 지울 딜에 자료·보고서·발주·불만 %건이 걸려 있다', stuck;
    END IF;

    -- 지우는 보고서에 확정 스냅샷이나 첨부가 붙어 있으면 마찬가지로 멈춘다.
    -- 나머지 자식(report_deal·report_source·report_activity·meeting_deal_analysis)은 CASCADE 다.
    SELECT
        (SELECT count(*) FROM public.report_submission WHERE report_id IN (SELECT id FROM dropped_report))
      + (SELECT count(*) FROM public.file WHERE report_id IN (SELECT id FROM dropped_report))
    INTO stuck;
    IF stuck <> 0 THEN
        RAISE EXCEPTION
            'activity_customer_company: 지울 보고서에 확정 스냅샷·첨부 %건이 걸려 있다', stuck;
    END IF;

    -- 지우는 일정이 남는 딜에 붙어 있으면 2번 백필이 빠뜨린 것이다.
    IF EXISTS (
        SELECT 1 FROM public.activity a
        WHERE a.id IN (SELECT id FROM dropped_activity)
          AND a.sales_deal_id IS NOT NULL
          AND a.sales_deal_id NOT IN (SELECT id FROM dropped_deal)
    ) THEN
        RAISE EXCEPTION
            'activity_customer_company: 남는 딜에 붙은 일정이 삭제 대상에 들어 있다';
    END IF;
END
$$;

DELETE FROM public.contract_next_meeting_suggestion
    WHERE sales_deal_id IN (SELECT id FROM dropped_deal);

-- report 의 자식은 CASCADE 이고 agent_run.report_id 는 SET NULL 이다.
DELETE FROM public.report
    WHERE id IN (SELECT id FROM dropped_report);

-- activity_companion 은 ON DELETE CASCADE 라 함께 사라진다.
DELETE FROM public.activity
    WHERE id IN (SELECT id FROM dropped_activity);

DELETE FROM public.sales_deal
    WHERE id IN (SELECT id FROM dropped_deal);

-- ---------------------------------------------------------------------------
-- 4~6. 일정의 고객사 칸
--
-- 회사는 담당자에게서 유도된다. 두 값이 어긋나지 않게 하는 것은 API 몫이고, 여기서는
-- 기존 행을 담당자의 회사로 채운 뒤 NOT NULL 로 잠근다.
-- ---------------------------------------------------------------------------

ALTER TABLE public.activity
    ADD COLUMN customer_company_id uuid REFERENCES public.customer_company (id);

UPDATE public.activity a
    SET customer_company_id = k.company_id
    FROM public.customer_contact k
    WHERE k.id = a.customer_contact_id;

DO $$
DECLARE
    remaining integer;
BEGIN
    SELECT count(*) INTO remaining
        FROM public.activity WHERE customer_company_id IS NULL;
    IF remaining <> 0 THEN
        RAISE EXCEPTION
            'activity_customer_company: 고객사를 못 채운 일정이 %건 남았다', remaining;
    END IF;
END
$$;

ALTER TABLE public.activity
    ALTER COLUMN customer_company_id SET NOT NULL;

CREATE INDEX activity_team_customer_company_idx
    ON public.activity (team_id, customer_company_id)
    WHERE deleted_at IS NULL;

COMMIT;
