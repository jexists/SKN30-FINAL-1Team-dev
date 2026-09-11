-- 고객 담당자의 일반 전화를 휴대폰·팩스와 분리한다.
--
-- 기존 phone은 휴대폰(필수)으로 유지한다. 대표번호·내선 등 일반 전화는 사람 중복
-- 판단의 기준이 아니므로 선택 컬럼으로 따로 보관한다.

BEGIN;

ALTER TABLE public.customer_contact
    ADD COLUMN telephone text;

COMMENT ON COLUMN public.customer_contact.telephone IS
    '일반 전화번호. 숫자만 저장하며, 휴대폰(phone)·팩스(fax)와 구분하는 선택 항목이다.';

COMMIT;
