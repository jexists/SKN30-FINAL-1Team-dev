-- 명함 원본을 등록된 고객 담당자와 연결한다.

BEGIN;

ALTER TABLE public.document
    ADD COLUMN customer_contact_id uuid
        REFERENCES public.customer_contact (id) ON DELETE SET NULL;

CREATE INDEX document_customer_contact_idx
    ON public.document (customer_contact_id)
    WHERE customer_contact_id IS NOT NULL;

COMMIT;
