BEGIN;

-- Supabase Auth 사용자와 public.member 를 잇는 유일한 연결 고리.
-- 로그인하지 않는 목업 구성원이 있으므로 NULL 을 허용한다.
-- 한 Supabase 사용자가 두 구성원에 연결되지 않도록 UNIQUE 로 막는다.
ALTER TABLE public.member
    ADD COLUMN auth_user_id uuid UNIQUE REFERENCES auth.users (id);

COMMENT ON COLUMN public.member.auth_user_id IS
    'Supabase auth.users.id. 인증은 Supabase 가, 팀·역할·활성 판단은 이 테이블이 담당한다.';

COMMIT;
