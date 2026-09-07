-- 보고서 작성 중 업로드한 원본을 보관하고 제출별 교정문·목적을 고정한다.
-- 기존 자료실 file의 부모·버전 제약과 보고서 본문 snapshot/hash는 변경하지 않는다.
BEGIN;

CREATE TABLE public.report_attachment (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    uploaded_by_member_id uuid NOT NULL REFERENCES public.member (id),
    report_id uuid REFERENCES public.report (id),
    file_name text NOT NULL CHECK (length(btrim(file_name)) BETWEEN 1 AND 254),
    storage_key text NOT NULL UNIQUE CHECK (btrim(storage_key) <> ''),
    media_type text NOT NULL CHECK (btrim(media_type) <> ''),
    byte_size bigint NOT NULL CHECK (byte_size > 0),
    extracted_text text CHECK (extracted_text IS NULL OR length(btrim(extracted_text)) BETWEEN 1 AND 50000),
    expires_at timestamptz,
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT report_attachment_lifecycle CHECK (
        (report_id IS NULL AND expires_at IS NOT NULL)
        OR (report_id IS NOT NULL AND expires_at IS NULL AND extracted_text IS NOT NULL)
    )
);
CREATE INDEX report_attachment_pending_idx ON public.report_attachment (expires_at)
    WHERE report_id IS NULL;
CREATE INDEX report_attachment_report_idx ON public.report_attachment (report_id)
    WHERE report_id IS NOT NULL;
ALTER TABLE public.report_attachment ENABLE ROW LEVEL SECURITY;

CREATE FUNCTION public.guard_report_attachment_update()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.report_id IS NOT NULL THEN
            RAISE EXCEPTION 'submitted report attachment is immutable';
        END IF;
        RETURN OLD;
    END IF;
    IF ROW(NEW.id, NEW.team_id, NEW.uploaded_by_member_id, NEW.file_name,
           NEW.storage_key, NEW.media_type, NEW.byte_size, NEW.uploaded_at)
       IS DISTINCT FROM
       ROW(OLD.id, OLD.team_id, OLD.uploaded_by_member_id, OLD.file_name,
           OLD.storage_key, OLD.media_type, OLD.byte_size, OLD.uploaded_at)
       OR (OLD.extracted_text IS NOT NULL AND NEW.extracted_text IS DISTINCT FROM OLD.extracted_text)
       OR (OLD.report_id IS NOT NULL AND NEW.report_id IS DISTINCT FROM OLD.report_id) THEN
        RAISE EXCEPTION 'report attachment original is immutable';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER report_attachment_immutable
    BEFORE UPDATE OR DELETE ON public.report_attachment
    FOR EACH ROW EXECUTE FUNCTION public.guard_report_attachment_update();

ALTER TABLE public.report_submission
    ADD COLUMN attachments_snapshot jsonb
    CHECK (attachments_snapshot IS NULL OR
        (jsonb_typeof(attachments_snapshot) = 'array' AND jsonb_array_length(attachments_snapshot) <= 10));
CREATE FUNCTION public.guard_report_submission_attachments_update()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.attachments_snapshot IS DISTINCT FROM OLD.attachments_snapshot THEN
        RAISE EXCEPTION 'report submission attachments are immutable';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER report_submission_attachments_immutable
    BEFORE UPDATE ON public.report_submission
    FOR EACH ROW EXECUTE FUNCTION public.guard_report_submission_attachments_update();

COMMENT ON TABLE public.report_attachment IS
    '보고서 원본 첨부. 미귀속 업로드는 24시간 후 정리하고 귀속 후에는 제출 이력에서 보존한다.';
COMMENT ON COLUMN public.report_submission.attachments_snapshot IS
    '제출 당시 원본 ID·메타데이터·목적·교정 추출문. 본문 domain snapshot과 별도로 불변이다. NULL은 과거 미보관 제출본.';
COMMIT;
