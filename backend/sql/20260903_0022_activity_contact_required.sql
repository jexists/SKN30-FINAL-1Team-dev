-- 담당자를 필수로 잠그고, 채울 수 있는 일정의 딜을 한 번 채운다.
--
-- 20260902_0019 가 범위 밖으로 미뤄 둔 customer_contact_id 의 NOT NULL 을 여기서 건다.
-- 담당자가 비어 있으면 계약관리 에이전트가 다음 미팅을 추천할 때 일정에 넣을 사람을 못
-- 정해 AI 브리핑이 아예 만들어지지 않는다. 0019 가 이미 비운 값이라 여기 남아 있다면
-- 그 뒤에 들어온 살아 있는 행이므로, 지우지 않고 멈춰서 사람이 보게 한다.
--
-- **딜(activity.sales_deal_id)은 잠그지 않는다.** 인사차 방문처럼 특정 영업 건을
-- 진전시키지 않는 만남이 있고, 거기에 딜을 강제하면 있지도 않은 딜이 만들어져 파이프라인이
-- 더러워진다. 대신 채울 수 있는 것만 여기서 한 번 채운다 — 지우는 행은 없다.
--   * 미팅하고 보고서를 쓴 일정은 어느 딜이었는지 보고서에 남아 있다(report_activity →
--     report_deal). 딜 하나짜리 레거시 보고서는 report.sales_deal_id 를 본다.
--   * 그것도 없고 고객사에 열린 딜이 하나뿐이면 그 딜로 본다. 고를 여지가 없는 경우다.
--   * 둘 다 아니면 비워 둔다. 앞으로 들어오는 일정은 등록 API 와 보고서 저장이 같은
--     규칙으로 채우므로, 이 백필은 그 규칙을 기존 데이터에 한 번 적용하는 것이다.
--
-- 딜의 고객사가 일정의 고객사와 다르면 쓰지 않는다 — API 가 그런 짝을 422 로 막는다.
-- deleted_at 이 찍힌 행도 같이 다룬다. NOT NULL 은 소프트 삭제와 무관하게 전체 행에 걸린다.
--
-- **DB 적용과 백엔드 배포는 붙여서 한다.** 담당자를 잠그는 것은 화면이 이미 담당자를
-- 필수로 받고 있어 어느 쪽을 먼저 해도 등록이 막히지는 않지만, 딜 보드의 '딜 추가' 폼이
-- 담당자를 보내기 시작하는 것은 배포 뒤다. 배포가 늦으면 그 사이 딜 등록이 NOT NULL 에
-- 막히므로 DB 적용 뒤 곧바로 배포한다.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. 보고서에서 딜을 역추적해 채운다
--
-- 보고서 하나에 딜이 여럿 달리므로 position(화면에 놓인 순서) 이 앞선 것을 대표로 본다.
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
-- 2. 고객사에 열린 딜이 하나뿐이면 그 딜
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
-- 3. 담당자를 잠근다
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    remaining integer;
BEGIN
    SELECT
        (SELECT count(*) FROM public.activity WHERE customer_contact_id IS NULL)
      + (SELECT count(*) FROM public.sales_deal WHERE customer_contact_id IS NULL)
    INTO remaining;
    IF remaining <> 0 THEN
        RAISE EXCEPTION
            'activity_contact_required: 담당자를 못 채운 행이 %건 남았다', remaining;
    END IF;
END
$$;

ALTER TABLE public.activity
    ALTER COLUMN customer_contact_id SET NOT NULL;

ALTER TABLE public.sales_deal
    ALTER COLUMN customer_contact_id SET NOT NULL;

COMMENT ON COLUMN public.activity.customer_contact_id IS
    '이 일정에서 만나는 사람. 비면 AI 브리핑을 만들 수 없어 필수다.';
COMMENT ON COLUMN public.sales_deal.customer_contact_id IS
    '이 딜의 대표 담당자. 다음 미팅 추천이 일정에 적을 사람이라 필수다.';
COMMENT ON COLUMN public.activity.sales_deal_id IS
    '이 일정이 무엇에 대한 영업 건인가. 인사차 방문처럼 딜이 없는 만남이 있어 비워 둘 수 있다. 비면 계약관리 에이전트가 그 일정을 보지 못한다.';

COMMIT;
