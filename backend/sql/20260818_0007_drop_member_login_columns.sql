-- 적용 보류. 0006 적용과 테스트 계정 4개 연결, 로그인 검증을 모두 마친 뒤에만 실행한다.
--
-- 이 파일을 적용하면 자체 로그인으로 되돌릴 수 없다. 실행 전 다음을 확인한다.
--   1. member.auth_user_id 가 로그인해야 하는 구성원 4명에 모두 채워져 있다.
--   2. 네 계정 모두 실제로 로그인해 팀·역할·데이터가 맞는 것을 확인했다.
--   3. app/models/workspace.py 와 scripts/seed_demo_auth.py 에서 두 컬럼을 함께 제거한다.

BEGIN;

-- 아무도 연결되지 않은 상태에서 지우면 로그인 수단이 사라진다.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.member WHERE active AND auth_user_id IS NOT NULL
    ) THEN
        RAISE EXCEPTION
            'drop blocked: no active member is linked to a Supabase auth user yet';
    END IF;
END $$;

ALTER TABLE public.member
    DROP COLUMN login_id,
    DROP COLUMN password_hash;

COMMIT;
