-- 전화 한 칸을 휴대폰과 팩스로 나눈다.
--
-- 기존 phone 은 그대로 휴대폰(필수)으로 남는다. 명함에는 대표번호·팩스가 함께 적혀 있어
-- 한 칸에 담으면 어느 번호인지 알 수 없다. 팩스는 사람을 찾는 값이 아니라 선택 항목이고,
-- 검색·필터·엑셀 임포트는 지금처럼 phone 만 본다.

BEGIN;

ALTER TABLE public.customer_contact
    ADD COLUMN fax text;

COMMENT ON COLUMN public.customer_contact.fax IS
    '팩스 번호. 숫자만 저장한다. 선택 항목이라 NULL 이 기본이다.';

COMMIT;
