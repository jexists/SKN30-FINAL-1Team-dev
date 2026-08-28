-- 영업 딜에 유입경로를 둔다.
--
-- 딜을 처음 넣을 때 "이 건이 어디서 들어왔는지" 를 함께 적는다. 지금까지는 고객
-- (customer_contact.source_code) 에만 있어서, 같은 고객에게서 여러 건이 들어오면
-- 건마다 다른 경로를 남길 수 없었다.
--
-- 코드 값은 customer_contact.source_code 와 같은 세트를 쓴다. 거기와 마찬가지로
-- 열거형 CHECK 나 룩업 테이블은 두지 않는다. 예전에 들어온 코드도 읽혀야 하고,
-- 쓰기는 스키마가 막는다. 기존 행은 채울 근거가 없어 NULL 로 둔다.

BEGIN;

ALTER TABLE public.sales_deal
    ADD COLUMN source_code text
        CHECK (source_code IS NULL OR btrim(source_code) <> '');

COMMENT ON COLUMN public.sales_deal.source_code IS
    '유입경로 코드. customer_contact.source_code 와 같은 세트이며 모르면 NULL 이다.';

COMMIT;
