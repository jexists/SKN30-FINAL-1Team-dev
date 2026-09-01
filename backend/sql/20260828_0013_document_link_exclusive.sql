-- 자료실 문서는 상품과 딜 중 하나에만 연결한다.
--
-- API 검증과 별개로 DB에서도 같은 규칙을 보장해, 다른 쓰기 경로가 생겨도
-- 두 연결 대상이 함께 저장되지 않게 한다. 기존 잘못된 데이터가 있으면
-- 조용히 삭제·수정하지 않고 먼저 실패시켜 운영자가 확인하도록 한다.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.document
        WHERE product_id IS NOT NULL
          AND sales_deal_id IS NOT NULL
    ) THEN
        RAISE EXCEPTION
            'document_link_conflict: existing document has product_id and sales_deal_id';
    END IF;
END
$$;

ALTER TABLE public.document
    ADD CONSTRAINT document_product_or_deal_check
    CHECK (NOT (product_id IS NOT NULL AND sales_deal_id IS NOT NULL));

COMMIT;
