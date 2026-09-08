-- 팀원마다 맡은 지역을 하나 둔다. 정하는 사람은 계정을 발급하는 어드민과 팀장이다.
--
-- 지금 팀 관리 표에는 직책과 역할만 있어 누가 어느 지역을 맡는지 화면 어디에도 없다.
-- 계정을 발급할 때 골라 두고 팀 관리에서 고칠 수 있게 한다.
--
-- 값은 customer_company.region_code 와 같은 코드 체계다. 나중에 지역별 실적을 셀 때 딜이
-- 가리키는 지역과 그대로 맞물려야 하므로 한글 이름이 아니라 코드로 저장한다.
--
-- NULL 은 "담당지역 미지정" 이고 화면은 그때 '—' 를 보여 준다. 이미 있는 팀원은 정해 둔
-- 근거가 없으므로 NULL 로 남긴다.

BEGIN;

-- 고를 수 있는 코드 목록은 DB 에 고정하지 않는다. customer_company.region_code 도 공백만
-- 막고 목록은 앱이 지킨다. 지역 하나를 늘릴 때마다 스키마를 바꾸게 되는 편이 더 나쁘다.
ALTER TABLE public.member
    ADD COLUMN region_code text
        CHECK (region_code IS NULL OR btrim(region_code) <> '');

COMMENT ON COLUMN public.member.region_code IS
    '팀원이 맡은 지역 코드. customer_company.region_code 와 같은 코드 체계다. NULL 이면 미지정이다.';

COMMIT;
