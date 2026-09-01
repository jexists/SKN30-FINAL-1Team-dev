-- OCR·요약 결과를 사람에게 보여 준 뒤 최종 저장할 수 있도록 승인 대기 상태를 추가한다.
-- 원본 파일은 먼저 저장하지만, 추출 결과 컬럼과 RAG 청크는 승인 전에는 채우지 않는다.

BEGIN;

ALTER TABLE public.file
    DROP CONSTRAINT IF EXISTS file_processing_status_check;

ALTER TABLE public.file
    ADD CONSTRAINT file_processing_status_check
    CHECK (
        processing_status IN (
            'uploaded',
            'processing',
            'review_required',
            'completed',
            'failed'
        )
    );

COMMIT;
