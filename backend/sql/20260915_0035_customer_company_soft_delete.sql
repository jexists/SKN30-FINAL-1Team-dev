-- 살아 있는 고객이 하나도 없는 고객사를 고르는 자리에서 감춘다.
--
-- 회사를 미리 등록해 두는 화면은 없다. 회사는 고객을 등록하는 길에만 생기므로, 그 회사의
-- 고객을 모두 지우면 회사만 남아 회사검색에 계속 나온다. 고객현황에서 지웠는데 회사검색에
-- 그대로 나온다는 말이 여기서 나온다.
--
-- 행을 실제로 지우면 안 된다. sales_deal, purchase_order, report, support_request,
-- sales_target, document, activity 가 customer_company 를 참조하고 있어 DELETE 는 외래키에
-- 막히고, 참조를 끊으면 지난 딜과 보고서에서 어느 회사였는지가 사라진다.
--
-- customer_contact, support_request, document 가 이미 쓰는 deleted_at 방식을 따른다.
-- 고르는 자리(회사검색)만 deleted_at IS NULL 을 보고, id 로 읽는 자리는 거르지 않아 지난
-- 기록에는 회사 이름이 그대로 남는다.

BEGIN;

ALTER TABLE public.customer_company
    ADD COLUMN deleted_at timestamptz;

COMMENT ON COLUMN public.customer_company.deleted_at IS
    '살아 있는 고객이 하나도 없어 회사검색에서 감춘 시각. 고객을 다시 등록하면 NULL 로 돌아온다.';

-- 회사검색은 늘 살아 있는 회사만 이름으로 찾는다.
CREATE INDEX customer_company_active_idx
    ON public.customer_company (team_id, name)
    WHERE deleted_at IS NULL;

-- 이미 고객이 모두 지워진 회사를 지금 기준에 맞춘다.
--
-- 고객이 한 번도 없던 회사는 건드리지 않는다. 앱은 고객을 지울 때만 회사를 감추므로,
-- 시드로 미리 넣어 둔 잠재 고객사(현재 개발 DB 에 3231 곳)까지 감추면 규칙보다 앞서 나가
-- 회사검색이 통째로 비어 버린다.
UPDATE public.customer_company AS c
   SET deleted_at = now()
 WHERE EXISTS (
           SELECT 1
             FROM public.customer_contact AS ct
            WHERE ct.company_id = c.id
       )
   AND NOT EXISTS (
           SELECT 1
             FROM public.customer_contact AS ct
            WHERE ct.company_id = c.id
              AND ct.deleted_at IS NULL
       );

COMMIT;
