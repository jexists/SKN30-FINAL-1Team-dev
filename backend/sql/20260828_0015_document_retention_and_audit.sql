-- 자료실 보관 정책과 승인·수정 이력.
-- 20260825_0005_document_summary.sql 및 20260828_0014_document_summary_approval.sql 적용 후 실행한다.

BEGIN;

ALTER TABLE public.file
    ADD COLUMN review_expires_at timestamptz,
    ADD COLUMN unapproved_expires_at timestamptz,
    ADD COLUMN approved_by_member_id uuid REFERENCES public.member (id),
    ADD COLUMN approved_at timestamptz;

CREATE INDEX file_review_expiry_idx
    ON public.file (review_expires_at)
    WHERE processing_status = 'review_required';

CREATE INDEX file_unapproved_expiry_idx
    ON public.file (unapproved_expires_at)
    WHERE processing_status <> 'completed';

CREATE TABLE public.document_file_audit (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    document_id uuid NOT NULL REFERENCES public.document (id) ON DELETE CASCADE,
    file_id uuid NOT NULL REFERENCES public.file (id) ON DELETE CASCADE,
    action_code text NOT NULL CHECK (
        action_code IN ('file_uploaded', 'summary_reprocess_requested', 'summary_approved')
    ),
    actor_member_id uuid NOT NULL REFERENCES public.member (id),
    before_snapshot jsonb,
    after_snapshot jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX document_file_audit_team_created_idx
    ON public.document_file_audit (team_id, created_at DESC);
CREATE INDEX document_file_audit_file_created_idx
    ON public.document_file_audit (file_id, created_at DESC);

ALTER TABLE public.document_file_audit ENABLE ROW LEVEL SECURITY;

COMMIT;
