-- 자료요약 Agent의 OCR 산출물·요약·RAG 청크 저장소.
-- baseline 및 20260823~20260824 후속 migration 적용 후 실행한다.

BEGIN;

ALTER TABLE public.file
    ADD COLUMN extracted_markdown text
        CHECK (extracted_markdown IS NULL OR btrim(extracted_markdown) <> ''),
    ADD COLUMN extracted_payload jsonb,
    ADD COLUMN summary_markdown text
        CHECK (summary_markdown IS NULL OR btrim(summary_markdown) <> ''),
    ADD COLUMN summary_payload jsonb,
    ADD COLUMN processing_error text
        CHECK (processing_error IS NULL OR btrim(processing_error) <> ''),
    ADD COLUMN processed_at timestamptz;

CREATE TABLE public.document_chunk (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    document_id uuid NOT NULL REFERENCES public.document (id) ON DELETE CASCADE,
    file_id uuid NOT NULL REFERENCES public.file (id) ON DELETE CASCADE,
    chunk_no integer NOT NULL CHECK (chunk_no >= 0),
    page_start integer CHECK (page_start IS NULL OR page_start >= 1),
    page_end integer CHECK (page_end IS NULL OR page_end >= 1),
    section text CHECK (section IS NULL OR btrim(section) <> ''),
    content text NOT NULL CHECK (btrim(content) <> ''),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (file_id, chunk_no)
);

CREATE INDEX document_chunk_team_idx ON public.document_chunk (team_id);
CREATE INDEX document_chunk_document_idx ON public.document_chunk (document_id);
CREATE INDEX document_chunk_file_idx ON public.document_chunk (file_id);

ALTER TABLE public.document_chunk ENABLE ROW LEVEL SECURITY;

COMMIT;
