-- 일정에 딜을 필수로 둔다. 그 전에 딜이 빈 일정을 채우거나 정리하고, 담당자도 함께 잠근다.
--
-- activity.sales_deal_id 는 "이 일정이 무엇에 대한 것인가" 다. 비어 있으면 그 일정은
-- 파이프라인에도 계약관리 에이전트에도 걸리지 않아 나중에 다시 찾을 자리가 없다.
-- 지금까지 캘린더에서 직접 등록한 일정에는 이 값이 아예 붙지 않았다(등록 모달에 딜 칸이
-- 없었다). 이번에 화면이 딜을 필수로 받고, 고를 딜이 없는 신규 고객사는 그 자리에서
-- 딜을 만들도록 바뀌었으므로 DB 도 함께 잠근다.
--
-- 채울 수 있는 것과 없는 것이 갈린다.
--   * 미팅하고 보고서를 쓴 일정은 어느 딜이었는지 보고서에 남아 있다(report_activity →
--     report_deal). 딜 하나짜리 레거시 보고서는 report.sales_deal_id 를 본다.
--   * 그것도 없고 고객사에 딜이 하나뿐이면 그 딜로 본다.
--   * 둘 다 아니면 근거가 없다. 20260902_0019 가 지운 '[지시] …' 일정과 같은 성격이라 지운다.
--     그 일정에 물린 보고서는 원본이 사라지면 근거를 잃으므로 함께 지운다.
--   * deleted_at 이 찍힌 행도 같이 다룬다. NOT NULL 은 소프트 삭제와 무관하게 전체 행에 걸린다.
--
-- 20260902_0019 가 범위 밖으로 미뤄 둔 customer_contact_id 의 NOT NULL 도 여기서 함께 건다.
-- 같은 테이블의 같은 종류 전환이라 따로 하면 같은 데이터를 두 번 정리하게 된다. 딜 보드의
-- '딜 추가' 폼도 이번에 담당자를 필수로 받도록 바뀌었다(이 값을 늘 null 로 보내고 있었다).
--
-- ON DELETE 는 지금처럼 두고 바꾸지 않는다. activity.sales_deal_id 에 CASCADE 를 걸면 딜을
-- 지울 때 그 딜의 일정과 보고서가 말없이 함께 사라진다. 앱은 딜을 deleted_at 으로만 지우므로
-- 실제로 행이 사라지는 곳은 이런 마이그레이션뿐이고, 그때는 0019 처럼 무엇이 걸려 있는지
-- 세어 보고 사람이 판단하는 편이 안전하다.
--
-- **백엔드 배포가 DB 적용보다 먼저다.** 이전 코드는 딜 없이도 일정을 등록하므로, DB 를 먼저
-- 잠그면 그 사이 등록이 NOT NULL 에 막힌다. 20260902_0019 와 방향이 반대이니 순서를 헷갈리지
-- 않게 두 파일을 함께 보고 적용한다.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. 보고서에서 딜을 역추적해 백필
--
-- 보고서 하나에 딜이 여럿 달리므로 position(화면에 놓인 순서) 이 앞선 것을 대표로 본다.
-- 딜의 고객사가 일정의 고객사와 다르면 쓰지 않는다 — 새 API 가 그런 짝을 422 로 막는다.
-- ---------------------------------------------------------------------------

WITH candidate AS (
    SELECT ra.activity_id, rd.sales_deal_id, 1 AS priority, rd.position AS ord
    FROM public.report_activity ra
    JOIN public.report_deal rd ON rd.report_id = ra.report_id
    UNION ALL
    -- 레거시 호환용 단일 딜. 신규 미팅 보고서는 NULL 이다(20260901_0016).
    SELECT r.source_activity_id, r.sales_deal_id, 2, NULL
    FROM public.report r
    WHERE r.source_activity_id IS NOT NULL
      AND r.sales_deal_id IS NOT NULL
),
picked AS (
    SELECT DISTINCT ON (c.activity_id)
        c.activity_id,
        c.sales_deal_id
    FROM candidate c
    JOIN public.activity a ON a.id = c.activity_id
    JOIN public.sales_deal d ON d.id = c.sales_deal_id
    WHERE a.sales_deal_id IS NULL
      AND d.customer_company_id = a.customer_company_id
    ORDER BY c.activity_id, c.priority, c.ord NULLS LAST, c.sales_deal_id
)
UPDATE public.activity a
    SET sales_deal_id = picked.sales_deal_id
    FROM picked
    WHERE a.id = picked.activity_id;

-- ---------------------------------------------------------------------------
-- 2. 고객사에 딜이 하나뿐이면 그 딜
--
-- 고를 여지가 없으므로 사람이 정하는 것과 같은 답이 된다. 둘 이상이면 손대지 않는다.
-- ---------------------------------------------------------------------------

WITH only_deal AS (
    -- HAVING 이 한 건으로 좁히므로 모아 놓은 배열의 첫 값이 그 한 건이다.
    -- uuid 에는 min() 이 없어 집계로 뽑을 수 없다.
    SELECT d.customer_company_id, (array_agg(d.id))[1] AS sales_deal_id
    FROM public.sales_deal d
    WHERE d.deleted_at IS NULL
    GROUP BY d.customer_company_id
    HAVING count(*) = 1
)
UPDATE public.activity a
    SET sales_deal_id = only_deal.sales_deal_id
    FROM only_deal
    WHERE a.customer_company_id = only_deal.customer_company_id
      AND a.sales_deal_id IS NULL;

-- ---------------------------------------------------------------------------
-- 3. 근거가 없는 일정 삭제
-- ---------------------------------------------------------------------------

CREATE TEMP TABLE dropped_activity ON COMMIT DROP AS
SELECT id FROM public.activity WHERE sales_deal_id IS NULL;

CREATE TEMP TABLE dropped_report ON COMMIT DROP AS
SELECT id FROM public.report
    WHERE source_activity_id IN (SELECT id FROM dropped_activity);

DO $$
DECLARE
    stuck integer;
BEGIN
    RAISE NOTICE '삭제 대상: 일정 % / 보고서 %',
        (SELECT count(*) FROM dropped_activity),
        (SELECT count(*) FROM dropped_report);

    -- 지우는 보고서에 확정 스냅샷이나 첨부가 붙어 있으면 조용히 지우지 않고 멈춘다.
    -- 나머지 자식(report_deal·report_source·report_activity·meeting_deal_analysis)은 CASCADE 다.
    SELECT
        (SELECT count(*) FROM public.report_submission WHERE report_id IN (SELECT id FROM dropped_report))
      + (SELECT count(*) FROM public.file WHERE report_id IN (SELECT id FROM dropped_report))
    INTO stuck;
    IF stuck <> 0 THEN
        RAISE EXCEPTION
            'activity_sales_deal_required: 지울 보고서에 확정 스냅샷·첨부 %건이 걸려 있다', stuck;
    END IF;

    -- 지우는 일정을 남는 보고서가 붙들고 있으면 멈춘다. report_activity 와 report_source 는
    -- activity 를 CASCADE 없이 참조하므로 그대로 지우면 외래키에 막힌다. 지우는 보고서의
    -- 자식은 report 삭제로 함께 사라지므로 여기서 세지 않는다.
    SELECT
        (SELECT count(*) FROM public.report_activity
            WHERE activity_id IN (SELECT id FROM dropped_activity)
              AND report_id NOT IN (SELECT id FROM dropped_report))
      + (SELECT count(*) FROM public.report_source
            WHERE source_activity_id IN (SELECT id FROM dropped_activity)
              AND report_id NOT IN (SELECT id FROM dropped_report))
    INTO stuck;
    IF stuck <> 0 THEN
        RAISE EXCEPTION
            'activity_sales_deal_required: 지울 일정을 남는 보고서가 %건 붙들고 있다', stuck;
    END IF;
END
$$;

-- report 의 자식은 CASCADE 이고 agent_run.report_id 는 SET NULL 이다.
DELETE FROM public.report
    WHERE id IN (SELECT id FROM dropped_report);

-- activity_companion 은 ON DELETE CASCADE 라 함께 사라진다.
DELETE FROM public.activity
    WHERE id IN (SELECT id FROM dropped_activity);

-- ---------------------------------------------------------------------------
-- 4. 잠그기
--
-- 20260902_0019 가 담당자를 이미 비웠으므로 여기서 남아 있으면 그 뒤에 들어온 살아 있는
-- 행이다. 지우지 않고 멈춰서 사람이 보게 한다.
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    remaining integer;
BEGIN
    SELECT
        (SELECT count(*) FROM public.activity WHERE sales_deal_id IS NULL)
      + (SELECT count(*) FROM public.activity WHERE customer_contact_id IS NULL)
      + (SELECT count(*) FROM public.sales_deal WHERE customer_contact_id IS NULL)
    INTO remaining;
    IF remaining <> 0 THEN
        RAISE EXCEPTION
            'activity_sales_deal_required: 딜·담당자를 못 채운 행이 %건 남았다', remaining;
    END IF;
END
$$;

ALTER TABLE public.activity
    ALTER COLUMN sales_deal_id SET NOT NULL;

ALTER TABLE public.activity
    ALTER COLUMN customer_contact_id SET NOT NULL;

ALTER TABLE public.sales_deal
    ALTER COLUMN customer_contact_id SET NOT NULL;

COMMENT ON COLUMN public.activity.sales_deal_id IS
    '이 일정이 무엇에 대한 영업 건인가. 비우면 파이프라인·계약관리 에이전트 어디에도 걸리지 않아 필수다.';
COMMENT ON COLUMN public.activity.customer_contact_id IS
    '이 일정에서 만나는 사람. 비면 AI 브리핑을 만들 수 없어 필수다.';
COMMENT ON COLUMN public.sales_deal.customer_contact_id IS
    '이 딜의 대표 담당자. 다음 미팅 추천이 일정에 적을 사람이라 필수다.';

COMMIT;
