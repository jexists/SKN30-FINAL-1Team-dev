-- 명함 등록에서는 일반 전화만 확인될 수 있으므로 휴대폰(phone)을 선택값으로 바꾼다.
-- 단건 API는 등록 경로별로 직접·사업자등록증은 phone, 명함은 telephone을 필수 검증한다.

BEGIN;

ALTER TABLE public.customer_contact
    ALTER COLUMN phone DROP NOT NULL;

ALTER TABLE public.customer_contact
    DROP CONSTRAINT IF EXISTS customer_contact_phone_check;

ALTER TABLE public.customer_contact
    ADD CONSTRAINT customer_contact_phone_check
    CHECK (phone IS NULL OR btrim(phone) <> '');

COMMENT ON COLUMN public.customer_contact.phone IS
    '휴대폰 번호. 명함 등록에서 일반 전화만 확인된 경우 비울 수 있으며 숫자만 저장한다.';

COMMIT;
