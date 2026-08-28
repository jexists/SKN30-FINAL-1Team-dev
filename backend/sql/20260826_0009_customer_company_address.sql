-- 고객사에 주소를 둔다.
--
-- 고객 등록 화면이 다음(카카오) 우편번호 서비스로 주소를 찾아 넣는다. 주소는 사람이 아니라
-- 회사에 붙는 값이라 customer_company 에 둔다. 회사 검색 목록도 같은 이름을 구분할 때
-- 사업자등록번호 대신 이 주소를 먼저 보여 준다.
--
-- postcode 와 address 는 우편번호 서비스가 돌려주는 값이고, address_detail 은 층·호수처럼
-- 사람이 직접 치는 부분이다. 기존 행은 채울 근거가 없어 NULL 로 둔다.

BEGIN;

ALTER TABLE public.customer_company
    ADD COLUMN postcode text
        CHECK (postcode IS NULL OR postcode ~ '^[0-9]{5}$'),
    ADD COLUMN address text,
    ADD COLUMN address_detail text;

COMMENT ON COLUMN public.customer_company.postcode IS
    '우편번호 5자리. 다음 우편번호 서비스가 주는 값이다.';
COMMENT ON COLUMN public.customer_company.address IS
    '주소. 도로명 또는 지번이며 사람이 고른 쪽을 그대로 저장한다.';
COMMENT ON COLUMN public.customer_company.address_detail IS
    '상세주소. 층·호수처럼 사람이 직접 적는 부분이다.';

COMMIT;
