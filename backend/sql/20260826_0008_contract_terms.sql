-- 계약서 양식이 요구하는 두 항목에 자리를 만든다.
--
-- 계약서 필수항목 중 나머지는 이미 있는 것으로 채워진다. 계약자정보(갑)(을)은 딜의
-- 고객사와 팀의 회사명·사업자등록번호에서 유도하고, 납품예상일자와 품목·수량·단가·
-- 금액은 딜:견적:계약이 1:1 이라 견적이 넣어 둔 값(quote_delivery_terms,
-- sales_deal_item)이 같은 행에 그대로 있다. 보증기간은 warranty_terms 다.
--
-- 남는 둘은 지금 어디에도 담을 데가 없어 컬럼으로 더한다. 둘 다 금액이나 날짜로
-- 표현할 수 없는 문구다. "납품 후 30일 이내", "상법 연이자 6%" 처럼 조건이 붙는다.
--
-- 20260826_0007 의 quote_delivery_terms 와 같은 모양이다. NULL 이면 아직 적지
-- 않았다는 뜻이고, 백필할 근거가 없으므로 기존 행은 NULL 로 둔다.

BEGIN;

ALTER TABLE public.sales_deal
    ADD COLUMN contract_payment_terms text
        CHECK (contract_payment_terms IS NULL OR btrim(contract_payment_terms) <> ''),
    ADD COLUMN contract_late_interest_terms text
        CHECK (contract_late_interest_terms IS NULL
               OR btrim(contract_late_interest_terms) <> '');

COMMENT ON COLUMN public.sales_deal.contract_payment_terms IS
    '물품대금 지급기일. "납품 후 30일 이내" 처럼 날짜로 표현할 수 없어 text 다.';
COMMENT ON COLUMN public.sales_deal.contract_late_interest_terms IS
    '대금연체 이자율. "상법 연이자 6%" 처럼 근거와 함께 적어 text 다.';

COMMIT;
