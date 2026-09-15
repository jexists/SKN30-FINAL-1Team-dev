BEGIN;

ALTER TABLE public.contract_next_meeting_suggestion
    ADD COLUMN IF NOT EXISTS target_date date,
    ADD COLUMN IF NOT EXISTS target_time time,
    ADD COLUMN IF NOT EXISTS selected_duration_minutes integer,
    ADD COLUMN IF NOT EXISTS excluded_dates jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS refresh_reason text,
    ADD COLUMN IF NOT EXISTS applied_activity_id uuid REFERENCES public.activity (id);

ALTER TABLE public.contract_next_meeting_suggestion
    DROP CONSTRAINT IF EXISTS contract_next_meeting_suggestion_status_code_check;

ALTER TABLE public.contract_next_meeting_suggestion
    ADD CONSTRAINT contract_next_meeting_suggestion_status_code_check
    CHECK (status_code IN ('pending', 'rejected', 'expired', 'accepted'));

ALTER TABLE public.contract_next_meeting_suggestion
    DROP CONSTRAINT IF EXISTS contract_next_meeting_suggestion_duration_check;

ALTER TABLE public.contract_next_meeting_suggestion
    ADD CONSTRAINT contract_next_meeting_suggestion_duration_check
    CHECK (selected_duration_minutes IS NULL OR selected_duration_minutes IN (30, 60, 90));

COMMENT ON COLUMN public.contract_next_meeting_suggestion.target_date IS
    '계약관리 Agent가 추천한 단 하나의 날짜.';
COMMENT ON COLUMN public.contract_next_meeting_suggestion.target_time IS
    '고객과 명시적으로 합의된 경우에만 있는 시작 시각.';
COMMENT ON COLUMN public.contract_next_meeting_suggestion.selected_duration_minutes IS
    '사용자가 추천 카드에서 선택한 30/60/90분.';

COMMIT;
