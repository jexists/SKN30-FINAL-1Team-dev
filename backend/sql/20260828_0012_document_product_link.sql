-- 자료실 문서를 상품에 붙인다.
--
-- 업로드 화면이 자료를 상품이나 딜 중 한쪽에 매단다. 딜은 sales_deal_id 로 이미
-- 붙일 수 있었지만 상품은 붙일 데가 없었다. 상품설명서·카탈로그처럼 딜과 무관하게
-- 상품에만 매이는 자료가 갈 곳이 필요하다.
--
-- 기존 고객사(customer_company_id)와 발주(purchase_order_id) 연결은 그대로 둔다.
-- 새로 고를 수는 없지만 이미 붙어 있는 자료가 목록에서 연결을 잃지 않아야 한다.
-- 기존 행은 채울 근거가 없어 NULL 로 둔다.

BEGIN;

ALTER TABLE public.document
    ADD COLUMN product_id uuid REFERENCES public.product (id);

COMMENT ON COLUMN public.document.product_id IS
    '연결된 상품. 딜에 매인 자료는 sales_deal_id 를 쓰며 둘 다 비면 연결 없는 자료다.';

-- customer_company_id 와 같은 이유의 부분 인덱스다. 상품 상세에서 자료를 훑는다.
CREATE INDEX document_product_idx
    ON public.document (product_id)
    WHERE product_id IS NOT NULL;

COMMIT;
