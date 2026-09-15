-- Every immutable report submission is searchable; briefing reads only each report's current one.
BEGIN;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE public.report_context_chunk (
    report_submission_id uuid PRIMARY KEY
        REFERENCES public.report_submission (id) ON DELETE CASCADE,
    report_id uuid NOT NULL REFERENCES public.report (id) ON DELETE CASCADE,
    team_id uuid NOT NULL REFERENCES public.team (id),
    content text NOT NULL CHECK (btrim(content) <> ''),
    embedding_vector vector,
    embedding_model text,
    indexed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT report_context_chunk_vector_model_check CHECK (
        (embedding_vector IS NULL AND embedding_model IS NULL)
        OR (embedding_vector IS NOT NULL AND embedding_model IS NOT NULL
            AND vector_dims(embedding_vector) IN (384, 1536))
    )
);

CREATE FUNCTION public.report_submission_context_text(snapshot jsonb)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT btrim(concat_ws(E'\n',
        snapshot ->> 'title',
        snapshot ->> 'body',
        snapshot ->> 'common_body',
        snapshot ->> 'unassigned_body',
        (
            SELECT string_agg(
                concat_ws(E'\n',
                    deal.value ->> 'deal_no_snapshot',
                    deal.value ->> 'deal_title_snapshot',
                    deal.value ->> 'title',
                    deal.value ->> 'body'
                ),
                E'\n'
            )
            FROM jsonb_array_elements(COALESCE(snapshot -> 'deals', '[]'::jsonb)) AS deal(value)
        )
    ));
$$;

CREATE FUNCTION public.index_report_submission_context()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    context_text text;
BEGIN
    context_text := public.report_submission_context_text(NEW.snapshot);
    IF context_text <> '' THEN
        INSERT INTO public.report_context_chunk (
            report_submission_id, report_id, team_id, content
        ) VALUES (NEW.id, NEW.report_id, NEW.team_id, context_text)
        ON CONFLICT (report_submission_id) DO UPDATE
        SET content = EXCLUDED.content,
            embedding_vector = NULL,
            embedding_model = NULL,
            indexed_at = now();
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER report_submission_context_index
AFTER INSERT ON public.report_submission
FOR EACH ROW EXECUTE FUNCTION public.index_report_submission_context();

INSERT INTO public.report_context_chunk (report_submission_id, report_id, team_id, content)
SELECT submission.id, submission.report_id, submission.team_id, context.content
FROM public.report_submission AS submission
CROSS JOIN LATERAL (
    SELECT public.report_submission_context_text(submission.snapshot) AS content
) AS context
WHERE context.content <> ''
ON CONFLICT (report_submission_id) DO NOTHING;

CREATE INDEX report_context_chunk_team_report_idx
    ON public.report_context_chunk (team_id, report_id);
CREATE INDEX report_context_chunk_keyword_idx
    ON public.report_context_chunk USING gin (to_tsvector('simple', content));
CREATE INDEX report_context_chunk_vector_384_idx ON public.report_context_chunk
    USING hnsw ((embedding_vector::vector(384)) vector_cosine_ops)
    WHERE vector_dims(embedding_vector) = 384;
CREATE INDEX report_context_chunk_vector_1536_idx ON public.report_context_chunk
    USING hnsw ((embedding_vector::vector(1536)) vector_cosine_ops)
    WHERE vector_dims(embedding_vector) = 1536;

ALTER TABLE public.report_context_chunk ENABLE ROW LEVEL SECURITY;
COMMIT;
