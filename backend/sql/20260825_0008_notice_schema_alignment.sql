-- Develop의 notice 관리 구조와 기존 runtime_schema_alignment의 임시 컬럼을 정리한다.
-- 0005_notice_management 이후 0007이 실행된 환경에서도 동일한 최종 스키마를 보장한다.

BEGIN;

DROP INDEX IF EXISTS public.notice_team_recipient_published_idx;

ALTER TABLE public.notice
    DROP COLUMN IF EXISTS recipient_member_id;

COMMIT;
