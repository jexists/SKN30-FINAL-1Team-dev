-- 견적·계약·발주의 서류별 메모를 딜 공용 메모와 분리한다.
--
-- 상세 화면에서 단계를 옮길 때 그 서류의 최소 정보(금액과 메모)를 함께 적는다.
-- 기존 memo 한 칸을 셋이 나눠 쓰면 나중에 적은 쪽이 앞의 것을 덮으므로 각자 갖는다.

BEGIN;

ALTER TABLE public.sales_deal
    ADD COLUMN quote_memo text,
    ADD COLUMN contract_memo text,
    ADD COLUMN order_memo text,
    ADD CONSTRAINT sales_deal_quote_memo_check
        CHECK (quote_memo IS NULL OR btrim(quote_memo) <> ''),
    ADD CONSTRAINT sales_deal_contract_memo_check
        CHECK (contract_memo IS NULL OR btrim(contract_memo) <> ''),
    ADD CONSTRAINT sales_deal_order_memo_check
        CHECK (order_memo IS NULL OR btrim(order_memo) <> '');

COMMENT ON COLUMN public.sales_deal.quote_memo IS
    '견적 메모. 단계를 견적 국면으로 옮길 때 적는 고객 요청사항 등이다.';
COMMENT ON COLUMN public.sales_deal.contract_memo IS
    '계약 메모. 단계를 계약 국면으로 옮길 때 적는 계약 관련 메모다.';
COMMENT ON COLUMN public.sales_deal.order_memo IS
    '발주 메모. 발주서(purchase_order)를 만들기 전에 남기는 발주 관련 메모다.';

COMMIT;
