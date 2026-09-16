-- 보여 주기만 하는 보고서 참고자료(extract_text=false)는 OCR·STT를 돌리지 않아 교정문이 빈 문자열이다.
-- NULL은 여전히 Storage 업로드 미완료 표식이므로 빈 문자열만 추가로 허용한다. 공백뿐인 문자열은 계속 거부한다.

BEGIN;

ALTER TABLE public.report_attachment
    DROP CONSTRAINT report_attachment_extracted_text_check,
    ADD CONSTRAINT report_attachment_extracted_text_check CHECK (
        extracted_text IS NULL
        OR extracted_text = ''
        OR length(btrim(extracted_text)) BETWEEN 1 AND 50000
    );

COMMIT;
