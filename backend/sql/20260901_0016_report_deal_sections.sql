-- 미팅 한 건을 report 한 행으로 저장하고, 딜별 본문/분석은 report_deal 자식으로 분리한다.
-- 기존 딜별 report 행은 source_activity_id별로 가장 먼저 만들어진 행에 합친다.
BEGIN;

CREATE TABLE public.report_deal (
    report_id uuid NOT NULL REFERENCES public.report (id) ON DELETE CASCADE,
    sales_deal_id uuid NOT NULL REFERENCES public.sales_deal (id),
    deal_snapshot jsonb NOT NULL CHECK (jsonb_typeof(deal_snapshot) = 'object'),
    content jsonb NOT NULL CHECK (jsonb_typeof(content) = 'object'),
    ai_evidence jsonb CHECK (ai_evidence IS NULL OR jsonb_typeof(ai_evidence) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (report_id, sales_deal_id)
);

CREATE INDEX report_deal_sales_deal_idx
    ON public.report_deal (sales_deal_id, report_id);

ALTER TABLE public.report_deal ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.report_deal IS
    '미팅 보고서 안의 딜별 스냅샷·본문·AI 분석. 부모 report는 미팅 공통 기록과 원문·상태만 가진다.';
COMMENT ON COLUMN public.report.sales_deal_id IS
    '레거시 호환용 단일 딜. 신규 미팅 보고서는 NULL이며 report_deal을 사용한다.';

CREATE TEMP TABLE meeting_report_merge ON COMMIT DROP AS
SELECT
    report.id AS old_report_id,
    first_value(report.id) OVER (
        PARTITION BY report.source_activity_id
        ORDER BY report.created_at, report.id
    ) AS canonical_report_id,
    report.source_activity_id
FROM public.report AS report
WHERE report.report_kind = 'meeting'
  AND report.source_activity_id IS NOT NULL;

CREATE UNIQUE INDEX meeting_report_merge_old_key
    ON meeting_report_merge (old_report_id);

-- 서로 다른 작성자나 공통 필드를 임의로 한 문서로 합치지는 않는다. 데이터는 그대로 둔 채 실패시킨다.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.report AS report
        JOIN meeting_report_merge AS merge ON merge.old_report_id = report.id
        GROUP BY merge.source_activity_id
        HAVING count(DISTINCT report.team_id) > 1
            OR count(DISTINCT report.author_member_id) > 1
            OR count(DISTINCT jsonb_build_array(report.recipient_member_id)) > 1
            OR count(DISTINCT report.report_date) > 1
            OR count(DISTINCT jsonb_build_array(report.period_start)) > 1
            OR count(DISTINCT jsonb_build_array(report.period_end)) > 1
            OR count(DISTINCT report.status_code) > 1
            OR count(DISTINCT report.template_snapshot) > 1
            OR count(DISTINCT jsonb_build_array(report.note)) > 1
            OR count(DISTINCT jsonb_build_array(report.reviewed_by_member_id)) > 1
            OR count(DISTINCT jsonb_build_array(report.reviewed_at)) > 1
            OR count(DISTINCT coalesce(report.source_snapshot, 'null'::jsonb)) > 1
            OR count(DISTINCT coalesce(report.content -> 'meeting_shared', 'null'::jsonb)) > 1
            -- title은 canonical 대표 제목으로 남기고 딜별 원본에도 보존한다. 그 밖에
            -- 부모로 승격되는 공통 필드는 서로 다르면 어느 값을 고를 수 없으므로 중단한다.
            OR count(DISTINCT (
                report.content - ARRAY[
                    'title', 'product', 'values', 'sales_deal', 'sales_deal_ids',
                    'evidence', 'ai_values', 'ai_evidence', 'ai_generated_at', 'meeting_shared'
                ]
            )) > 1
    ) THEN
        RAISE EXCEPTION 'meeting report rows require manual reconciliation before consolidation';
    END IF;
END
$$;

-- 딜별로 달랐던 구 원문은 출처 메타데이터와 함께 모두 보존한다. 합친 결과가 현재 API
-- 계약을 넘으면 임의로 자르지 않고 전체 migration을 중단한다.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM (
            SELECT
                merge.canonical_report_id,
                CASE
                    WHEN count(DISTINCT report.transcript)
                         FILTER (WHERE report.transcript IS NOT NULL) <= 1
                    THEN max(report.transcript)
                    ELSE string_agg(
                        format(
                            E'<<< migration metadata; not spoken | legacy_report_id=%s | sales_deal_id=%s >>>\n%s',
                            report.id,
                            coalesce(report.sales_deal_id::text, 'NULL'),
                            report.transcript
                        ),
                        E'\n\n' ORDER BY report.created_at, report.id
                    ) FILTER (WHERE report.transcript IS NOT NULL)
                END AS transcript
            FROM meeting_report_merge AS merge
            JOIN public.report AS report ON report.id = merge.old_report_id
            GROUP BY merge.canonical_report_id
        ) AS grouped
        WHERE char_length(grouped.transcript) > 50000
    ) THEN
        RAISE EXCEPTION 'merged meeting transcript exceeds 50000 characters';
    END IF;
END
$$;

-- 구 통합보고서가 가리킨 딜을 해석할 수 없으면 그 ID를 버리지 않고 migration을 멈춘다.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.report AS report
        CROSS JOIN LATERAL jsonb_array_elements_text(
            CASE
                WHEN jsonb_typeof(report.content -> 'sales_deal_ids') = 'array'
                THEN report.content -> 'sales_deal_ids'
                ELSE '[]'::jsonb
            END
        ) AS value(id)
        LEFT JOIN public.sales_deal AS deal
          ON deal.id = CASE
              WHEN value.id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
              THEN value.id::uuid
          END
        WHERE report.report_kind = 'meeting'
          AND report.source_activity_id IS NOT NULL
          AND deal.id IS NULL
    ) THEN
        RAISE EXCEPTION 'meeting report contains an invalid or missing sales_deal_id';
    END IF;
END
$$;

-- 단일 딜 행과 구 통합 행을 먼저 같은 후보 집합으로 편다. 한 행이 sales_deal_id와
-- sales_deal_ids 양쪽에 같은 딜을 담은 자기 중복도 여기 들어오며, 내용이 같으면 뒤에서 접힌다.
CREATE TEMP TABLE meeting_report_deal_candidate ON COMMIT DROP AS
SELECT
    merge.canonical_report_id,
    report.id AS old_report_id,
    report.sales_deal_id,
    CASE
        WHEN jsonb_typeof(report.content -> 'sales_deal') = 'object'
             AND report.content -> 'sales_deal' ->> 'id' = report.sales_deal_id::text
        THEN report.content -> 'sales_deal'
        ELSE jsonb_build_object(
            'id', deal.id::text,
            'label', deal.deal_no,
            'note', coalesce(deal.title, '')
        )
    END AS deal_snapshot,
    report.content - ARRAY[
        'time', 'hospital', 'dept', 'contact', 'place', 'attachments', 'approver',
        'activities', 'meeting_shared', 'sales_deal', 'sales_deal_ids'
    ] AS content,
    CASE
        WHEN jsonb_typeof(report.ai_evidence) = 'object' THEN report.ai_evidence
        ELSE NULL
    END AS ai_evidence,
    report.created_at,
    report.updated_at
FROM meeting_report_merge AS merge
JOIN public.report AS report ON report.id = merge.old_report_id
JOIN public.sales_deal AS deal ON deal.id = report.sales_deal_id
WHERE report.sales_deal_id IS NOT NULL
UNION ALL
SELECT
    merge.canonical_report_id,
    report.id AS old_report_id,
    deal.id,
    CASE
        WHEN jsonb_typeof(report.content -> 'sales_deal') = 'object'
             AND report.content -> 'sales_deal' ->> 'id' = deal.id::text
        THEN report.content -> 'sales_deal'
        ELSE jsonb_build_object(
            'id', deal.id::text,
            'label', deal.deal_no,
            'note', coalesce(deal.title, '')
        )
    END,
    report.content - ARRAY[
        'time', 'hospital', 'dept', 'contact', 'place', 'attachments', 'approver',
        'activities', 'meeting_shared', 'sales_deal', 'sales_deal_ids'
    ],
    CASE
        WHEN jsonb_typeof(report.ai_evidence) = 'object' THEN report.ai_evidence
        ELSE NULL
    END,
    report.created_at,
    report.updated_at
FROM meeting_report_merge AS merge
JOIN public.report AS report ON report.id = merge.old_report_id
CROSS JOIN LATERAL jsonb_array_elements_text(
    CASE
        WHEN jsonb_typeof(report.content -> 'sales_deal_ids') = 'array'
        THEN report.content -> 'sales_deal_ids'
        ELSE '[]'::jsonb
    END
) AS value(id)
JOIN public.sales_deal AS deal
  ON deal.id = CASE
      WHEN value.id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
      THEN value.id::uuid
  END
WHERE jsonb_typeof(report.content -> 'sales_deal_ids') = 'array';

CREATE INDEX meeting_report_deal_candidate_key
    ON meeting_report_deal_candidate (canonical_report_id, sales_deal_id);

-- 같은 미팅·딜을 가리키는 서로 다른 legacy 행의 실제 저장 단위가 다르면 어느 한쪽도
-- 고르지 않는다. 자기 중복이나 완전히 같은 중복만 안전하게 접을 수 있다.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM meeting_report_deal_candidate AS candidate
        GROUP BY candidate.canonical_report_id, candidate.sales_deal_id
        HAVING count(DISTINCT candidate.deal_snapshot) > 1
            OR count(DISTINCT candidate.content) > 1
            OR count(DISTINCT coalesce(candidate.ai_evidence, 'null'::jsonb)) > 1
    ) THEN
        RAISE EXCEPTION 'conflicting legacy report deal candidates require manual reconciliation';
    END IF;
END
$$;

-- 동일 후보는 한 자식으로 접되 원본 행들의 최초 생성·최종 수정 시각은 범위로 보존한다.
INSERT INTO public.report_deal (
    report_id,
    sales_deal_id,
    deal_snapshot,
    content,
    ai_evidence,
    created_at,
    updated_at
)
SELECT
    candidate.canonical_report_id,
    candidate.sales_deal_id,
    min(candidate.deal_snapshot::text)::jsonb,
    min(candidate.content::text)::jsonb,
    min(candidate.ai_evidence::text)::jsonb,
    min(candidate.created_at),
    max(candidate.updated_at)
FROM meeting_report_deal_candidate AS candidate
GROUP BY candidate.canonical_report_id, candidate.sales_deal_id;

-- 딜 근거가 전혀 없는 레거시 보고서 여러 건은 어느 본문을 자식으로 보낼지 알 수 없다.
-- 한 건은 원형 보존할 수 있지만 여러 건은 unique 적용 전에 수동 정리가 필요하다.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM meeting_report_merge AS merge
        GROUP BY merge.canonical_report_id
        HAVING count(*) > 1
           AND NOT EXISTS (
               SELECT 1
               FROM public.report_deal AS section
               WHERE section.report_id = merge.canonical_report_id
           )
    ) THEN
        RAISE EXCEPTION 'meeting reports without deal references require manual reconciliation';
    END IF;
END
$$;

-- 딜 참조가 없는 canonical 행에 딜 본문이 남아 있는데 같은 미팅의 다른 행에서 자식이
-- 만들어진 경우, 이 본문은 공통/미지정인지 특정 딜인지 자동 판정할 수 없다. 부모에
-- 숨겨 두거나 지우지 않고 수동 정리를 요구한다.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.report AS canonical
        WHERE canonical.report_kind = 'meeting'
          AND canonical.source_activity_id IS NOT NULL
          AND canonical.sales_deal_id IS NULL
          AND jsonb_typeof(canonical.content -> 'sales_deal_ids') IS DISTINCT FROM 'array'
          AND EXISTS (
              SELECT 1
              FROM public.report_deal AS section
              WHERE section.report_id = canonical.id
          )
          AND (
              canonical.content ?| ARRAY[
                  'product', 'values', 'sales_deal', 'evidence',
                  'ai_values', 'ai_evidence', 'ai_generated_at'
              ]
              OR canonical.ai_evidence IS NOT NULL
          )
    ) THEN
        RAISE EXCEPTION 'canonical meeting report has unscoped deal content; manual reconciliation required';
    END IF;
END
$$;

-- 부모에는 공통 입력과 공통/미지정 AI 본문만 남긴다. 구 데이터가 딜마다 서로 다른
-- 원문을 저장했다면 어느 하나도 버리지 않고 딜 번호를 붙여 한 원문으로 합친다.
UPDATE public.report AS canonical
SET content = CASE
        WHEN canonical.sales_deal_id IS NOT NULL
          OR jsonb_typeof(canonical.content -> 'sales_deal_ids') = 'array'
        THEN canonical.content - ARRAY[
            'product', 'values', 'sales_deal', 'sales_deal_ids', 'evidence',
            'ai_values', 'ai_evidence', 'ai_generated_at'
        ]
        ELSE canonical.content
    END,
    sales_deal_id = CASE
        WHEN EXISTS (
            SELECT 1 FROM public.report_deal AS section WHERE section.report_id = canonical.id
        ) THEN NULL
        ELSE canonical.sales_deal_id
    END,
    ai_evidence = CASE
        WHEN canonical.sales_deal_id IS NOT NULL
          OR jsonb_typeof(canonical.content -> 'sales_deal_ids') = 'array'
        THEN NULL
        ELSE canonical.ai_evidence
    END,
    transcript = grouped.transcript,
    created_at = grouped.created_at,
    updated_at = grouped.updated_at
FROM (
    SELECT
        merge.canonical_report_id,
        CASE
            WHEN count(DISTINCT report.transcript)
                 FILTER (WHERE report.transcript IS NOT NULL) <= 1
            THEN max(report.transcript)
            ELSE string_agg(
                format(
                    E'<<< migration metadata; not spoken | legacy_report_id=%s | sales_deal_id=%s >>>\n%s',
                    report.id,
                    coalesce(report.sales_deal_id::text, 'NULL'),
                    report.transcript
                ),
                E'\n\n' ORDER BY report.created_at, report.id
            ) FILTER (WHERE report.transcript IS NOT NULL)
        END AS transcript,
        min(report.created_at) AS created_at,
        max(report.updated_at) AS updated_at
    FROM meeting_report_merge AS merge
    JOIN public.report AS report ON report.id = merge.old_report_id
    GROUP BY merge.canonical_report_id
) AS grouped
WHERE canonical.id = grouped.canonical_report_id;

-- 연결 테이블과 첨부는 canonical report로 합쳐 원본 연결을 보존한다.
INSERT INTO public.report_activity (report_id, activity_id)
SELECT merge.canonical_report_id, link.activity_id
FROM meeting_report_merge AS merge
JOIN public.report_activity AS link ON link.report_id = merge.old_report_id
ON CONFLICT (report_id, activity_id) DO NOTHING;

DELETE FROM public.report_activity AS link
USING meeting_report_merge AS merge
WHERE link.report_id = merge.old_report_id
  AND merge.old_report_id <> merge.canonical_report_id;

UPDATE public.file AS file
SET report_id = merge.canonical_report_id
FROM meeting_report_merge AS merge
WHERE file.report_id = merge.old_report_id
  AND merge.old_report_id <> merge.canonical_report_id;

-- 실행 이력의 source_refs도 삭제될 report id 대신 canonical id를 가리킨다.
UPDATE public.agent_run AS run
SET source_refs = jsonb_set(
    run.source_refs,
    '{report_id}',
    to_jsonb(merge.canonical_report_id::text),
    false
)
FROM meeting_report_merge AS merge
WHERE run.source_refs ->> 'report_id' = merge.old_report_id::text
  AND merge.old_report_id <> merge.canonical_report_id;

WITH expanded AS (
    SELECT
        run.id AS run_id,
        item.ordinality,
        coalesce(merge.canonical_report_id::text, item.value) AS mapped_id
    FROM public.agent_run AS run
    CROSS JOIN LATERAL jsonb_array_elements_text(
        CASE
            WHEN jsonb_typeof(run.source_refs -> 'report_ids') = 'array'
            THEN run.source_refs -> 'report_ids'
            ELSE '[]'::jsonb
        END
    )
        WITH ORDINALITY AS item(value, ordinality)
    LEFT JOIN meeting_report_merge AS merge ON merge.old_report_id::text = item.value
    WHERE jsonb_typeof(run.source_refs -> 'report_ids') = 'array'
), unique_ids AS (
    SELECT run_id, mapped_id, min(ordinality) AS first_position
    FROM expanded
    GROUP BY run_id, mapped_id
), mapped AS (
    SELECT run_id, jsonb_agg(to_jsonb(mapped_id) ORDER BY first_position) AS ids
    FROM unique_ids
    GROUP BY run_id
)
UPDATE public.agent_run AS run
SET source_refs = jsonb_set(run.source_refs, '{report_ids}', mapped.ids, false)
FROM mapped
WHERE run.id = mapped.run_id;

DELETE FROM public.report AS report
USING meeting_report_merge AS merge
WHERE report.id = merge.old_report_id
  AND merge.old_report_id <> merge.canonical_report_id;

DROP INDEX IF EXISTS public.report_source_activity_sales_deal_key;
CREATE UNIQUE INDEX report_source_activity_meeting_key
    ON public.report (source_activity_id)
    WHERE report_kind = 'meeting' AND source_activity_id IS NOT NULL;

COMMIT;
