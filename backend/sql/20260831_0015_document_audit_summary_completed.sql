-- 자동 저장되는 요약 완료 이력을 document_file_audit에 기록할 수 있도록 허용한다.
-- 20260828_0015_document_retention_and_audit.sql 적용 후 실행한다.

BEGIN;

ALTER TABLE public.document_file_audit
    DROP CONSTRAINT IF EXISTS document_file_audit_action_code_check;

ALTER TABLE public.document_file_audit
    ADD CONSTRAINT document_file_audit_action_code_check
    CHECK (
        action_code IN (
            'file_uploaded',
            'summary_reprocess_requested',
            'summary_completed',
            'summary_approved'
        )
    );

COMMIT;
