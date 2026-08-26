-- 로컬·배포 코드와 기존 Supabase 스키마/데이터의 실행 정합성을 맞춘다.
-- 기존 notice 행은 전체 공지(NULL)로 유지하며, 비표준 source_code는
-- 의미를 임의로 바꾸지 않고 NULL로 되돌린다.

ALTER TABLE public.notice
    ADD COLUMN IF NOT EXISTS recipient_member_id uuid REFERENCES public.member (id);

CREATE INDEX IF NOT EXISTS notice_team_recipient_published_idx
    ON public.notice (team_id, recipient_member_id, published_at DESC);

UPDATE public.customer_contact
SET source_code = NULL
WHERE source_code = 'manual';
