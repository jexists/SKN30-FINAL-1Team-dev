-- 자료실 자료를 지울 수 있게 한다. 지우는 건 팀장뿐이다.
--
-- 행을 실제로 지우면 안 된다. file 이 ON DELETE 옵션 없이 document 를 참조하므로
-- DELETE 는 외래키 오류로 막히고, 파일 행을 먼저 지우면 OCR·요약 결과(file.extracted_*,
-- summary_*)와 감사 기록(document_file_audit)이 함께 사라진다.
--
-- sales_deal, purchase_order, report, notice, customer_contact 가 이미 쓰는 deleted_at
-- 방식을 따른다. 목록·상세와 RAG 검색은 deleted_at IS NULL 만 본다. 스토리지 원본과
-- document_chunk 는 그대로 남겨 되살릴 여지를 없애지 않는다.

BEGIN;

ALTER TABLE public.document
    ADD COLUMN deleted_at timestamptz;

COMMENT ON COLUMN public.document.deleted_at IS
    '삭제 시각. NULL 이면 살아 있는 자료다. 팀장만 채울 수 있다.';

-- 목록과 상세가 늘 살아 있는 자료만 찾는다. 지운 자료가 쌓여도 그쪽은 훑지 않는다.
CREATE INDEX document_active_idx
    ON public.document (id)
    WHERE deleted_at IS NULL;

COMMIT;
