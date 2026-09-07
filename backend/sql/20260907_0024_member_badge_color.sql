-- 담당자 이름표에 쓸 색을 팀원마다 하나씩 둔다. 정하는 사람은 팀장뿐이다.
--
-- 팀장이 '팀 전체' 로 볼 때 일정·딜·일일보고 목록에는 여러 담당자의 줄이 섞인다. 지금
-- 담당자 이름표는 모두 같은 회색이라 이름을 하나씩 읽어야 누구 것인지 알 수 있다. 팀장이
-- 고른 색을 그대로 이름표 바탕으로 써서 색만 보고 갈라지게 한다.
--
-- NULL 은 "아직 안 정했다" 는 뜻이고 화면은 그때 기존 회색을 쓴다. 새로 들어온 사람도
-- NULL 이라 색을 정해 주기 전까지는 지금과 똑같이 보인다.

BEGIN;

-- 화면이 그대로 style 에 넣는 값이라 모양을 DB 에서 좁힌다. '#' + 소문자 16진 6자리만
-- 받는다. 색 이름(red)이나 rgb() 같은 다른 표기를 섞으면 저장된 값으로 명도를 셈해
-- 글자색을 정하는 쪽이 갈라진다.
ALTER TABLE public.member
    ADD COLUMN badge_color text
        CHECK (badge_color ~ '^#[0-9a-f]{6}$');

COMMENT ON COLUMN public.member.badge_color IS
    '담당자 이름표 바탕색. #rrggbb 소문자다. NULL 이면 미지정이고 화면은 기본 회색을 쓴다. 팀장만 고칠 수 있다.';

-- 지금 개발 DB 에 들어 있는 표본 담당자 넷에만 은은한 기본값을 준다. 표본 화면이 처음부터
-- 알록달록하면 이름표가 아니라 색이 먼저 읽힌다.
--
-- 여기 넷은 scripts/seed_sample_bracelet.py 의 OWNER_EMAILS 와 같은 계정이다. 고를 수 있는
-- 색을 이 넷으로 제한하는 것이 아니다. 팀장은 팀 관리에서 진한 원색을 포함해 아무 색이나
-- 고를 수 있고, 그 값이 이 컬럼을 그대로 덮는다.
UPDATE public.member AS m
   SET badge_color = seed.color
  FROM (VALUES
            ('jungia21@naver.com', '#d6e4f7'),  -- 정주애: 연한 파랑
            ('bt1@naver.com', '#d8eedd'),       -- 김팀원: 연한 초록
            ('bt2@naver.com', '#e4dcf3'),       -- 박팀투: 연한 보라
            ('bt3@naver.com', '#f7e3ce')        -- 이팀삼: 연한 주황
       ) AS seed (email, color)
 WHERE lower(m.email) = seed.email
   AND m.badge_color IS NULL;

COMMIT;
