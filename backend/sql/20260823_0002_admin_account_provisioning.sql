-- 어드민 계정 발급(/admin)을 위한 스키마 변경.
--
-- 지금까지 로그인 계정은 Supabase Dashboard 에서 사람이 만들고 public.member 행도
-- 손으로 넣었다. 이 변경 이후로는 어드민이 화면에서 계정을 발급하고, Supabase Auth 의
-- invite 가 메일 발송과 비밀번호 설정을 대신한다.
--
-- 계정 발급 권한의 근거는 DB 가 아니라 ADMIN_USER_IDS 환경변수다. member 행만
-- 고쳐서는 어드민이 될 수 없다.

BEGIN;

ALTER TABLE public.team
    ADD COLUMN company_name text
        CHECK (company_name IS NULL OR btrim(company_name) <> ''),
    ADD COLUMN department text
        CHECK (department IS NULL OR btrim(department) <> ''),
    -- 하이픈 없이 10자리로만 저장한다. 화면에 보일 하이픈은 프론트가 붙인다.
    ADD COLUMN business_no text
        CHECK (business_no IS NULL OR business_no ~ '^[0-9]{10}$');

COMMENT ON COLUMN public.team.business_no IS
    '사업자등록번호 10자리. 하이픈 없이 저장한다.';

-- 이메일의 주인은 auth.users 다. 여기 값은 어드민 목록 화면이 팀별로 훑기 위한 사본이다.
-- 사용자가 이메일을 바꿀 수 있는 화면이 없으므로 지금은 어긋날 경로가 없다.
ALTER TABLE public.member
    ADD COLUMN email text CHECK (email IS NULL OR btrim(email) <> '');

COMMENT ON COLUMN public.member.email IS
    'auth.users.email 의 사본. 권한 판단에는 쓰지 않고 어드민 목록 표시에만 쓴다.';

-- 기존 행에는 email 이 없다. NULL 은 서로 충돌하지 않으므로 부분 인덱스로 둔다.
CREATE UNIQUE INDEX member_email_uq
    ON public.member (lower(email)) WHERE email IS NOT NULL;

COMMIT;

-- 적용 후 수동으로 해야 하는 일 (실제 UUID 는 저장소에 두지 않는다):
--
--   1. Supabase Dashboard > Authentication > Users 에서 어드민 계정 하나를 만든다.
--   2. 그 user id 를 백엔드 ADMIN_USER_IDS 에 넣는다.
--   3. 어드민 전용 팀과 member 행을 넣는다. 이 팀은 다른 팀 조회에 섞이지 않는다.
--      모든 라우터가 team_id 로 스코프를 걸기 때문이다.
--
--   INSERT INTO public.team (id, name) VALUES ('<team-uuid>', 'SalesLuv 운영');
--   INSERT INTO public.member (id, team_id, display_name, role_code, email)
--   VALUES ('<auth-user-uuid>', '<team-uuid>', '운영자', 'manager', '<admin-email>');
