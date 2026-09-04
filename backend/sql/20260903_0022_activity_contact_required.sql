-- 딜과 일정의 대표 담당자를 필수로 잠근다.
--
-- 20260902_0019 가 범위 밖으로 미뤄 둔 customer_contact_id 의 NOT NULL 을 여기서 건다.
-- 담당자가 비어 있으면 계약관리 에이전트가 다음 미팅을 추천할 때 일정에 넣을 사람을 못
-- 정해 AI 브리핑이 아예 만들어지지 않는다. 0019 가 이미 비운 값이라 여기 남아 있다면
-- 그 뒤에 들어온 살아 있는 행이므로, 지우지 않고 멈춰서 사람이 보게 한다.
--
-- **딜(activity.sales_deal_id)은 건드리지 않는다.** 일정에 어느 딜인지는 미팅 전에 정하지
-- 않는다 — 미팅을 마치고 보고서를 쓸 때 딜을 0개 이상 고르는 흐름이 있고(#124), 그쪽이
-- 정하는 값이다. 이 마이그레이션은 담당자만 본다. 지우는 행도, 채우는 딜도 없다.
--
-- **적용 직전에 담당자가 빈 행을 한 번 더 확인한다.** 딜 등록 폼이 담당자를 묻기 시작하는
-- 것은 이 브랜치 배포 뒤라, 그 사이에 만들어진 딜은 담당자가 비어 가드에 걸린다. 걸리면
-- customer_contact_id IS NULL 인 행을 찾아 채운 뒤 적용한다.
--
-- **DB 적용과 백엔드 배포를 붙여서 한다.** 딜 등록 폼이 담당자를 보내기 시작하는 것은
-- 배포 뒤라, 배포가 늦으면 그 사이 딜 등록이 NOT NULL 에 막힌다.

BEGIN;

-- ---------------------------------------------------------------------------
-- 담당자를 잠근다
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

COMMIT;
