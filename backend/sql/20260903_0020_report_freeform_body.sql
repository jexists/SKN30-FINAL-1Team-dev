-- 모든 보고서를 제목과 자유 본문 하나로 통일한다.
-- 본문은 사람이 확정한 값만 structured_values -> content.values -> 구 top-level
-- content 순서로 읽는다. AI 초안·원문·메타데이터는 저장 양식 필드인 척해도 사용하지 않는다.
BEGIN;
SET LOCAL lock_timeout = '5s';

-- 검증과 변환 사이에 새 레거시 값이 들어오지 않게 같은 트랜잭션에서 쓰기를 막는다.
LOCK TABLE public.report, public.report_deal, public.report_submission
    IN SHARE ROW EXCLUSIVE MODE;

-- jsonb_each/jsonb_array_elements가 안전하고 필드 순서가 하나로 결정되는 행만 변환한다.
DO $$
BEGIN
    IF EXISTS (
        WITH entity AS (
            SELECT
                'report' AS entity_type,
                report.id::text AS entity_id,
                report.template_snapshot,
                report.structured_values,
                report.content
            FROM public.report AS report
            WHERE report.report_kind IN ('meeting', 'daily', 'weekly', 'monthly')
            UNION ALL
            SELECT
                'report_deal',
                section.report_id::text || '/' || section.sales_deal_id::text,
                report.template_snapshot,
                section.structured_values,
                section.content
            FROM public.report_deal AS section
            JOIN public.report AS report ON report.id = section.report_id
            WHERE report.report_kind = 'meeting'
        )
        SELECT 1
        FROM entity
        WHERE jsonb_typeof(template_snapshot) IS DISTINCT FROM 'object'
           OR jsonb_typeof(template_snapshot -> 'fields') IS DISTINCT FROM 'array'
           OR jsonb_typeof(structured_values) IS DISTINCT FROM 'object'
           OR jsonb_typeof(content) IS DISTINCT FROM 'object'
           OR (
               content ? 'values'
               AND jsonb_typeof(content -> 'values') IS DISTINCT FROM 'object'
           )
    ) OR EXISTS (
        WITH entity AS (
            SELECT report.id::text AS entity_id, report.template_snapshot
            FROM public.report AS report
            WHERE report.report_kind IN ('meeting', 'daily', 'weekly', 'monthly')
            UNION ALL
            SELECT
                section.report_id::text || '/' || section.sales_deal_id::text,
                report.template_snapshot
            FROM public.report_deal AS section
            JOIN public.report AS report ON report.id = section.report_id
            WHERE report.report_kind = 'meeting'
        ), field AS (
            SELECT entity.entity_id, item.value
            FROM entity
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE
                    WHEN jsonb_typeof(entity.template_snapshot -> 'fields') = 'array'
                    THEN entity.template_snapshot -> 'fields'
                    ELSE '[]'::jsonb
                END
            ) AS item(value)
        )
        SELECT 1
        FROM field
        WHERE jsonb_typeof(value) IS DISTINCT FROM 'object'
           OR jsonb_typeof(value -> 'id') IS DISTINCT FROM 'string'
           OR nullif(btrim(value ->> 'id'), '') IS NULL
    ) OR EXISTS (
        WITH entity AS (
            SELECT report.id::text AS entity_id, report.template_snapshot
            FROM public.report AS report
            WHERE report.report_kind IN ('meeting', 'daily', 'weekly', 'monthly')
            UNION ALL
            SELECT
                section.report_id::text || '/' || section.sales_deal_id::text,
                report.template_snapshot
            FROM public.report_deal AS section
            JOIN public.report AS report ON report.id = section.report_id
            WHERE report.report_kind = 'meeting'
        )
        SELECT 1
        FROM entity
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE
                WHEN jsonb_typeof(entity.template_snapshot -> 'fields') = 'array'
                THEN entity.template_snapshot -> 'fields'
                ELSE '[]'::jsonb
            END
        ) AS field(value)
        GROUP BY entity.entity_id, field.value ->> 'id'
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'report body migration requires valid unique template fields';
    END IF;
END
$$;

-- 동일한 문자열의 구 사본만 접는다. 비문자, 미선언, 보안 필드, 서로 다른 사본,
-- 기존 본문 옆의 별도 값은 어느 쪽이 정답인지 추측하지 않고 중단한다.
DO $$
BEGIN
    IF EXISTS (
        WITH entity AS (
            SELECT
                'report' AS entity_type,
                report.id::text AS entity_id,
                report.body,
                report.template_snapshot,
                report.structured_values,
                report.content,
                report.report_kind <> 'meeting'
                    OR (
                        report.sales_deal_id IS NOT NULL
                        AND NOT EXISTS (
                            SELECT 1
                            FROM public.report_deal AS section
                            WHERE section.report_id = report.id
                        )
                    ) AS folds_to_body
            FROM public.report AS report
            WHERE report.report_kind IN ('meeting', 'daily', 'weekly', 'monthly')
            UNION ALL
            SELECT
                'report_deal',
                section.report_id::text || '/' || section.sales_deal_id::text,
                section.body,
                report.template_snapshot,
                section.structured_values,
                section.content,
                true
            FROM public.report_deal AS section
            JOIN public.report AS report ON report.id = section.report_id
            WHERE report.report_kind = 'meeting'
        ), field AS (
            SELECT
                entity.entity_type,
                entity.entity_id,
                item.value ->> 'id' AS field_id
            FROM entity
            CROSS JOIN LATERAL jsonb_array_elements(entity.template_snapshot -> 'fields')
                AS item(value)
        ), legacy_value AS (
            SELECT
                entity.entity_type,
                entity.entity_id,
                'structured' AS source,
                item.key,
                item.value
            FROM entity
            CROSS JOIN LATERAL jsonb_each(entity.structured_values) AS item
            UNION ALL
            SELECT
                entity.entity_type,
                entity.entity_id,
                'values',
                item.key,
                item.value
            FROM entity
            CROSS JOIN LATERAL jsonb_each(
                CASE
                    WHEN jsonb_typeof(entity.content -> 'values') = 'object'
                    THEN entity.content -> 'values'
                    ELSE '{}'::jsonb
                END
            ) AS item
            UNION ALL
            SELECT
                entity.entity_type,
                entity.entity_id,
                'top',
                field.field_id,
                entity.content -> field.field_id
            FROM entity
            JOIN field USING (entity_type, entity_id)
            WHERE entity.content ? field.field_id
            UNION ALL
            SELECT
                entity.entity_type,
                entity.entity_id,
                'top_body',
                'body',
                entity.content -> 'body'
            FROM entity
            WHERE entity.content ? 'body'
            UNION ALL
            SELECT
                entity.entity_type,
                entity.entity_id,
                'column',
                'body',
                to_jsonb(entity.body)
            FROM entity
            WHERE entity.body IS NOT NULL
        ), material AS (
            SELECT
                legacy_value.*,
                jsonb_typeof(legacy_value.value) AS value_type,
                legacy_value.value #>> '{}' AS text_value
            FROM legacy_value
            WHERE CASE jsonb_typeof(legacy_value.value)
                WHEN 'null' THEN false
                WHEN 'string' THEN btrim(legacy_value.value #>> '{}') <> ''
                ELSE true
            END
        ), bad AS (
            SELECT entity_type, entity_id
            FROM material
            WHERE value_type <> 'string'
            UNION ALL
            SELECT material.entity_type, material.entity_id
            FROM material
            WHERE material.source IN ('structured', 'values')
              AND material.key <> 'body'
              AND NOT EXISTS (
                  SELECT 1
                  FROM field
                  WHERE field.entity_type = material.entity_type
                    AND field.entity_id = material.entity_id
                    AND field.field_id = material.key
              )
            UNION ALL
            SELECT entity_type, entity_id
            FROM material
            WHERE regexp_replace(lower(key), '[^a-z0-9]', '', 'g') IN (
                'activity', 'activities', 'attachment', 'attachments', 'aievidence',
                'aigeneratedat', 'aivalues', 'contextlookups', 'crmcontext',
                'dealassessment', 'inputsnapshot', 'meetinganalysis', 'meetingshared',
                'ml', 'mlresult', 'outputsnapshot', 'rawpayload', 'rawtranscript',
                'requestsnapshot', 'sourcesnapshot', 'transcript', 'time', 'hospital',
                'dept', 'contact', 'product', 'place', 'title', 'approver', 'evidence',
                'salesdeal', 'salesdealids'
            )
            UNION ALL
            SELECT material.entity_type, material.entity_id
            FROM material
            JOIN entity USING (entity_type, entity_id)
            WHERE nullif(btrim(entity.body), '') IS NOT NULL
              AND material.key <> 'body'
            UNION ALL
            SELECT material.entity_type, material.entity_id
            FROM material
            JOIN entity USING (entity_type, entity_id)
            WHERE NOT entity.folds_to_body
            UNION ALL
            SELECT material.entity_type, material.entity_id
            FROM material
            JOIN entity USING (entity_type, entity_id)
            WHERE material.key = 'body'
              AND material.source <> 'column'
              AND nullif(btrim(entity.body), '') IS NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM field
                  WHERE field.entity_type = material.entity_type
                    AND field.entity_id = material.entity_id
                    AND field.field_id = 'body'
              )
            UNION ALL
            SELECT entity_type, entity_id
            FROM material
            WHERE value_type = 'string'
            GROUP BY entity_type, entity_id, key
            HAVING count(DISTINCT text_value) > 1
        )
        SELECT 1 FROM bad
    ) THEN
        RAISE EXCEPTION 'report body migration would discard or guess legacy values';
    END IF;
END
$$;

-- 0017 이후 구 서버가 저장한 공통/미지정 본문도 정규 컬럼으로만 읽을 수 있게 옮긴다.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.report AS report
        CROSS JOIN LATERAL (
            SELECT
                report.content #> '{meeting_shared,common_report,body}' AS legacy_common,
                report.content #> '{meeting_shared,unassigned_report,body}' AS legacy_unassigned
        ) AS legacy
        WHERE report.report_kind = 'meeting'
          AND (
              (
                  legacy.legacy_common IS NOT NULL
                  AND jsonb_typeof(legacy.legacy_common) NOT IN ('string', 'null')
              )
              OR (
                  legacy.legacy_unassigned IS NOT NULL
                  AND jsonb_typeof(legacy.legacy_unassigned) NOT IN ('string', 'null')
              )
              OR (
                  nullif(btrim(report.common_body), '') IS NOT NULL
                  AND nullif(btrim(legacy.legacy_common #>> '{}'), '') IS NOT NULL
                  AND btrim(report.common_body) <> btrim(legacy.legacy_common #>> '{}')
              )
              OR (
                  nullif(btrim(report.unassigned_body), '') IS NOT NULL
                  AND nullif(btrim(legacy.legacy_unassigned #>> '{}'), '') IS NOT NULL
                  AND btrim(report.unassigned_body) <> btrim(legacy.legacy_unassigned #>> '{}')
              )
              OR char_length(legacy.legacy_common #>> '{}') > 50000
              OR char_length(legacy.legacy_unassigned #>> '{}') > 50000
          )
    ) THEN
        RAISE EXCEPTION 'meeting shared body requires reconciliation';
    END IF;
END
$$;

-- 확정본은 해시와 불변 트리거 때문에 고치지 않는다. body-only가 아닌 확정본이 있으면
-- 배포 전 별도 읽기 호환 정책을 정하도록 migration 자체를 중단한다.
DO $$
BEGIN
    IF EXISTS (
        WITH submission AS (
            SELECT stored.id, stored.snapshot, report.report_kind
            FROM public.report_submission AS stored
            JOIN public.report AS report ON report.id = stored.report_id
            WHERE report.report_kind IN ('meeting', 'daily', 'weekly', 'monthly')
        ), node AS (
            SELECT id, report_kind, 'report' AS part, snapshot AS value
            FROM submission
            UNION ALL
            SELECT submission.id, submission.report_kind, 'deal', item.value
            FROM submission
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE
                    WHEN submission.report_kind = 'meeting'
                     AND jsonb_typeof(submission.snapshot -> 'deals') = 'array'
                    THEN submission.snapshot -> 'deals'
                    ELSE '[]'::jsonb
                END
            ) AS item(value)
        )
        SELECT 1
        FROM submission
        WHERE jsonb_typeof(snapshot) IS DISTINCT FROM 'object'
           OR snapshot ->> 'report_kind' IS DISTINCT FROM report_kind
           OR (
               report_kind = 'meeting'
               AND (
                   jsonb_typeof(snapshot -> 'deals') IS DISTINCT FROM 'array'
                   OR jsonb_array_length(
                       CASE
                           WHEN jsonb_typeof(snapshot -> 'deals') = 'array'
                           THEN snapshot -> 'deals'
                           ELSE '[]'::jsonb
                       END
                   ) = 0
               )
           )
           OR (
               report_kind <> 'meeting'
               AND (
                   jsonb_typeof(snapshot -> 'body') IS DISTINCT FROM 'string'
                   OR nullif(btrim(snapshot ->> 'body'), '') IS NULL
               )
           )
           OR (
               snapshot ? 'common_body'
               AND jsonb_typeof(snapshot -> 'common_body') NOT IN ('string', 'null')
           )
           OR (
               snapshot ? 'unassigned_body'
               AND jsonb_typeof(snapshot -> 'unassigned_body') NOT IN ('string', 'null')
           )
           OR char_length(snapshot ->> 'body') > 50000
           OR char_length(snapshot ->> 'common_body') > 50000
           OR char_length(snapshot ->> 'unassigned_body') > 50000
    ) OR EXISTS (
        WITH submission AS (
            SELECT stored.id, stored.snapshot, report.report_kind
            FROM public.report_submission AS stored
            JOIN public.report AS report ON report.id = stored.report_id
            WHERE report.report_kind IN ('meeting', 'daily', 'weekly', 'monthly')
        ), node AS (
            SELECT id, report_kind, 'report' AS part, snapshot AS value
            FROM submission
            UNION ALL
            SELECT submission.id, submission.report_kind, 'deal', item.value
            FROM submission
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE
                    WHEN submission.report_kind = 'meeting'
                     AND jsonb_typeof(submission.snapshot -> 'deals') = 'array'
                    THEN submission.snapshot -> 'deals'
                    ELSE '[]'::jsonb
                END
            ) AS item(value)
        )
        SELECT 1
        FROM node
        WHERE jsonb_typeof(value) IS DISTINCT FROM 'object'
           OR jsonb_typeof(value -> 'structured_values') IS DISTINCT FROM 'object'
           OR value -> 'structured_values' <> '{}'::jsonb
           OR (
               part = 'deal'
               AND (
                   jsonb_typeof(value -> 'body') IS DISTINCT FROM 'string'
                   OR nullif(btrim(value ->> 'body'), '') IS NULL
                   OR char_length(value ->> 'body') > 50000
               )
           )
           OR (
               value ? 'body'
               AND jsonb_typeof(value -> 'body') NOT IN ('string', 'null')
           )
    ) THEN
        RAISE EXCEPTION 'legacy immutable report submissions require reconciliation';
    END IF;
END
$$;

CREATE TEMP TABLE legacy_single_deal_report ON COMMIT DROP AS
SELECT report.id
FROM public.report AS report
WHERE report.report_kind = 'meeting'
  AND report.sales_deal_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM public.report_deal AS section WHERE section.report_id = report.id
  );

UPDATE public.report AS report
SET common_body = coalesce(
        report.common_body,
        nullif(btrim(report.content #>> '{meeting_shared,common_report,body}'), '')
    ),
    unassigned_body = coalesce(
        report.unassigned_body,
        nullif(btrim(report.content #>> '{meeting_shared,unassigned_report,body}'), '')
    )
WHERE report.report_kind = 'meeting';

-- 기간 보고서의 구 항목 값을 저장된 양식 순서로 이어 본문을 만든다.
WITH source AS (
    SELECT
        report.id,
        report.structured_values,
        report.content,
        CASE
            WHEN jsonb_typeof(report.template_snapshot -> 'fields') = 'array'
            THEN report.template_snapshot -> 'fields'
            ELSE '[]'::jsonb
        END AS fields
    FROM public.report AS report
    WHERE report.report_kind IN ('meeting', 'daily', 'weekly', 'monthly')
      AND nullif(btrim(report.body), '') IS NULL
), candidate AS (
    SELECT
        source.id,
        string_agg(selected.body, E'\n\n' ORDER BY field.position) AS body
    FROM source
    CROSS JOIN LATERAL jsonb_array_elements(source.fields)
        WITH ORDINALITY AS field(value, position)
    CROSS JOIN LATERAL (SELECT field.value ->> 'id' AS id) AS field_id
    CROSS JOIN LATERAL (
        SELECT coalesce(
            CASE
                WHEN jsonb_typeof(source.structured_values -> field_id.id) = 'string'
                 AND btrim(source.structured_values ->> field_id.id) <> ''
                THEN source.structured_values ->> field_id.id
            END,
            CASE
                WHEN jsonb_typeof(source.content -> 'values' -> field_id.id) = 'string'
                 AND btrim(source.content -> 'values' ->> field_id.id) <> ''
                THEN source.content -> 'values' ->> field_id.id
            END,
            CASE
                WHEN jsonb_typeof(source.content -> field_id.id) = 'string'
                 AND btrim(source.content ->> field_id.id) <> ''
                THEN source.content ->> field_id.id
            END
        ) AS body
    ) AS selected
    WHERE field_id.id IS NOT NULL
      AND regexp_replace(lower(field_id.id), '[^a-z0-9]', '', 'g') NOT IN (
          'activity', 'activities', 'attachment', 'attachments', 'aievidence',
          'aigeneratedat', 'aivalues', 'contextlookups', 'crmcontext', 'dealassessment',
          'inputsnapshot', 'meetinganalysis', 'meetingshared', 'ml', 'mlresult',
          'outputsnapshot',
          'rawpayload', 'rawtranscript', 'requestsnapshot', 'sourcesnapshot', 'transcript',
          'time', 'hospital', 'dept', 'contact', 'product', 'place', 'title', 'approver',
          'evidence', 'salesdeal', 'salesdealids'
      )
    GROUP BY source.id
)
UPDATE public.report AS report
SET body = candidate.body
FROM candidate
WHERE report.id = candidate.id
  AND candidate.body IS NOT NULL;

-- 0016 이후에도 구 API로 저장된 단일 딜 미팅은 sales_deal_id가 하나로 확정돼 있다.
-- 그 경우에만 부모의 본문과 딜 메타데이터를 정규 report_deal 한 건으로 옮긴다.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM legacy_single_deal_report AS legacy
        JOIN public.report AS report ON report.id = legacy.id
        WHERE nullif(btrim(report.body), '') IS NULL
           OR char_length(report.body) > 50000
    ) THEN
        RAISE EXCEPTION 'legacy single-deal meeting has no valid body';
    END IF;
END
$$;

INSERT INTO public.report_deal (
    report_id,
    sales_deal_id,
    deal_snapshot,
    content,
    ai_evidence,
    created_at,
    updated_at,
    position,
    deal_no_snapshot,
    deal_title_snapshot,
    title,
    body,
    structured_values
)
SELECT
    report.id,
    deal.id,
    jsonb_build_object(
        'id', deal.id::text,
        'label', deal.deal_no,
        'note', coalesce(deal.title, '')
    ),
    report.content - ARRAY[
        'time', 'hospital', 'dept', 'contact', 'place', 'attachments', 'approver',
        'activities', 'meeting_shared', 'sales_deal', 'sales_deal_ids'
    ],
    report.ai_evidence,
    report.created_at,
    report.updated_at,
    0,
    deal.deal_no,
    deal.title,
    coalesce(report.title, nullif(btrim(report.content ->> 'title'), '')),
    report.body,
    report.structured_values
FROM legacy_single_deal_report AS legacy
JOIN public.report AS report ON report.id = legacy.id
JOIN public.sales_deal AS deal ON deal.id = report.sales_deal_id;

UPDATE public.report AS report
SET sales_deal_id = NULL,
    title = coalesce(report.title, nullif(btrim(report.content ->> 'title'), '')),
    body = NULL,
    structured_values = '{}'::jsonb,
    ai_evidence = NULL,
    content = report.content - ARRAY[
        'product', 'values', 'sales_deal', 'sales_deal_ids', 'evidence',
        'ai_values', 'ai_evidence', 'ai_generated_at'
    ]
FROM legacy_single_deal_report AS legacy
WHERE report.id = legacy.id;

-- 미팅의 사람 확정값은 report_deal에 있다. 부모의 저장 양식으로 같은 방식으로 읽는다.
WITH source AS (
    SELECT
        section.report_id,
        section.sales_deal_id,
        section.structured_values,
        section.content,
        CASE
            WHEN jsonb_typeof(report.template_snapshot -> 'fields') = 'array'
            THEN report.template_snapshot -> 'fields'
            ELSE '[]'::jsonb
        END AS fields
    FROM public.report_deal AS section
    JOIN public.report AS report ON report.id = section.report_id
    WHERE report.report_kind = 'meeting'
      AND nullif(btrim(section.body), '') IS NULL
), candidate AS (
    SELECT
        source.report_id,
        source.sales_deal_id,
        string_agg(selected.body, E'\n\n' ORDER BY field.position) AS body
    FROM source
    CROSS JOIN LATERAL jsonb_array_elements(source.fields)
        WITH ORDINALITY AS field(value, position)
    CROSS JOIN LATERAL (SELECT field.value ->> 'id' AS id) AS field_id
    CROSS JOIN LATERAL (
        SELECT coalesce(
            CASE
                WHEN jsonb_typeof(source.structured_values -> field_id.id) = 'string'
                 AND btrim(source.structured_values ->> field_id.id) <> ''
                THEN source.structured_values ->> field_id.id
            END,
            CASE
                WHEN jsonb_typeof(source.content -> 'values' -> field_id.id) = 'string'
                 AND btrim(source.content -> 'values' ->> field_id.id) <> ''
                THEN source.content -> 'values' ->> field_id.id
            END,
            CASE
                WHEN jsonb_typeof(source.content -> field_id.id) = 'string'
                 AND btrim(source.content ->> field_id.id) <> ''
                THEN source.content ->> field_id.id
            END
        ) AS body
    ) AS selected
    WHERE field_id.id IS NOT NULL
      AND regexp_replace(lower(field_id.id), '[^a-z0-9]', '', 'g') NOT IN (
          'activity', 'activities', 'attachment', 'attachments', 'aievidence',
          'aigeneratedat', 'aivalues', 'contextlookups', 'crmcontext', 'dealassessment',
          'inputsnapshot', 'meetinganalysis', 'meetingshared', 'ml', 'mlresult',
          'outputsnapshot',
          'rawpayload', 'rawtranscript', 'requestsnapshot', 'sourcesnapshot', 'transcript',
          'time', 'hospital', 'dept', 'contact', 'product', 'place', 'title', 'approver',
          'evidence', 'salesdeal', 'salesdealids'
      )
    GROUP BY source.report_id, source.sales_deal_id
)
UPDATE public.report_deal AS section
SET body = candidate.body
FROM candidate
WHERE section.report_id = candidate.report_id
  AND section.sales_deal_id = candidate.sales_deal_id
  AND candidate.body IS NOT NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.report AS report
        WHERE report.report_kind IN ('daily', 'weekly', 'monthly')
          AND nullif(btrim(report.body), '') IS NULL
    ) OR EXISTS (
        SELECT 1
        FROM public.report AS report
        WHERE report.report_kind = 'meeting'
          AND (
              NOT EXISTS (
                  SELECT 1
                  FROM public.report_deal AS section
                  WHERE section.report_id = report.id
              )
              OR EXISTS (
                  SELECT 1
                  FROM public.report_deal AS section
                  WHERE section.report_id = report.id
                    AND nullif(btrim(section.body), '') IS NULL
              )
          )
    ) THEN
        RAISE EXCEPTION 'report body migration produced an empty canonical report';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.report WHERE char_length(body) > 50000
    ) OR EXISTS (
        SELECT 1 FROM public.report_deal WHERE char_length(body) > 50000
    ) THEN
        RAISE EXCEPTION 'migrated report body exceeds 50000 characters';
    END IF;
END
$$;

-- 구 top-level 필드를 제거하고 정규 본문만 content.values에 거울상으로 남긴다.
-- 미팅 부모에는 공통/미지정 본문과 메타데이터만 남긴다.
WITH fields AS (
    SELECT
        report.id,
        coalesce(
            array_agg(field.value ->> 'id' ORDER BY field.position)
                FILTER (
                    WHERE jsonb_typeof(field.value) = 'object'
                      AND field.value ? 'id'
                      AND regexp_replace(
                          lower(field.value ->> 'id'), '[^a-z0-9]', '', 'g'
                      ) NOT IN (
                          'activity', 'activities', 'attachment', 'attachments', 'aievidence',
                          'aigeneratedat', 'aivalues', 'contextlookups', 'crmcontext',
                          'dealassessment', 'inputsnapshot', 'meetinganalysis', 'meetingshared',
                          'ml', 'mlresult', 'outputsnapshot', 'rawpayload', 'rawtranscript', 'requestsnapshot',
                          'sourcesnapshot', 'transcript', 'time', 'hospital', 'dept', 'contact',
                          'product', 'place', 'title', 'approver', 'evidence', 'salesdeal',
                          'salesdealids'
                      )
                ),
            ARRAY[]::text[]
        ) AS ids
    FROM public.report AS report
    LEFT JOIN LATERAL jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(report.template_snapshot -> 'fields') = 'array'
            THEN report.template_snapshot -> 'fields'
            ELSE '[]'::jsonb
        END
    ) WITH ORDINALITY AS field(value, position) ON true
    WHERE report.report_kind IN ('meeting', 'daily', 'weekly', 'monthly')
    GROUP BY report.id
)
UPDATE public.report AS report
SET content = (report.content - fields.ids - 'values') || jsonb_build_object(
        'values',
        CASE
            WHEN nullif(btrim(report.body), '') IS NULL THEN '{}'::jsonb
            ELSE jsonb_build_object('body', report.body)
        END
    ),
    structured_values = '{}'::jsonb
FROM fields
WHERE report.id = fields.id;

WITH fields AS (
    SELECT
        section.report_id,
        section.sales_deal_id,
        coalesce(
            array_agg(field.value ->> 'id' ORDER BY field.position)
                FILTER (
                    WHERE jsonb_typeof(field.value) = 'object'
                      AND field.value ? 'id'
                      AND regexp_replace(
                          lower(field.value ->> 'id'), '[^a-z0-9]', '', 'g'
                      ) NOT IN (
                          'activity', 'activities', 'attachment', 'attachments', 'aievidence',
                          'aigeneratedat', 'aivalues', 'contextlookups', 'crmcontext',
                          'dealassessment', 'inputsnapshot', 'meetinganalysis', 'meetingshared',
                          'ml', 'mlresult', 'outputsnapshot', 'rawpayload', 'rawtranscript', 'requestsnapshot',
                          'sourcesnapshot', 'transcript', 'time', 'hospital', 'dept', 'contact',
                          'product', 'place', 'title', 'approver', 'evidence', 'salesdeal',
                          'salesdealids'
                      )
                ),
            ARRAY[]::text[]
        ) AS ids
    FROM public.report_deal AS section
    JOIN public.report AS report ON report.id = section.report_id
    LEFT JOIN LATERAL jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(report.template_snapshot -> 'fields') = 'array'
            THEN report.template_snapshot -> 'fields'
            ELSE '[]'::jsonb
        END
    ) WITH ORDINALITY AS field(value, position) ON true
    WHERE report.report_kind = 'meeting'
    GROUP BY section.report_id, section.sales_deal_id
)
UPDATE public.report_deal AS section
SET content = (section.content - fields.ids - 'values') || jsonb_build_object(
        'values',
        CASE
            WHEN nullif(btrim(section.body), '') IS NULL THEN '{}'::jsonb
            ELSE jsonb_build_object('body', section.body)
        END
    ),
    structured_values = '{}'::jsonb
FROM fields
WHERE section.report_id = fields.report_id
  AND section.sales_deal_id = fields.sales_deal_id;

-- 본문을 옮긴 뒤에 저장 양식을 바꾼다. 먼저 바꾸면 구 필드 순서를 잃는다.
UPDATE public.report AS report
SET template_snapshot = jsonb_build_object(
    'id', CASE report.report_kind
        WHEN 'meeting' THEN 'builtin-meeting-freeform'
        WHEN 'daily' THEN 'builtin-daily-freeform'
        WHEN 'weekly' THEN 'builtin-weekly-freeform'
        ELSE 'builtin-monthly-freeform'
    END,
    'name', CASE report.report_kind
        WHEN 'meeting' THEN '미팅 보고서'
        WHEN 'daily' THEN '일일보고서'
        WHEN 'weekly' THEN '주간보고서'
        ELSE '월간보고서'
    END,
    'owner', '',
    'updated', '',
    'fields', jsonb_build_array(jsonb_build_object(
        'id', 'body',
        'label', '보고서 본문',
        'type', 'textarea',
        'required', true,
        'aiFilled', true,
        'placeholder', CASE report.report_kind
            WHEN 'meeting' THEN '미팅에서 논의한 내용을 입력하세요.'
            WHEN 'daily' THEN '하루 동안 진행한 업무와 미팅 내용을 자유롭게 작성하세요.'
            WHEN 'weekly' THEN '한 주 동안의 성과와 다음 계획을 자유롭게 작성하세요.'
            ELSE '한 달 동안의 실적과 다음 계획을 자유롭게 작성하세요.'
        END
    ))
)
WHERE report.report_kind IN ('meeting', 'daily', 'weekly', 'monthly');

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.report AS report
        WHERE report.report_kind IN ('meeting', 'daily', 'weekly', 'monthly')
          AND (
              jsonb_typeof(report.template_snapshot -> 'fields') IS DISTINCT FROM 'array'
              OR jsonb_array_length(
                  CASE
                      WHEN jsonb_typeof(report.template_snapshot -> 'fields') = 'array'
                      THEN report.template_snapshot -> 'fields'
                      ELSE '[]'::jsonb
                  END
              ) <> 1
              OR report.template_snapshot #>> '{fields,0,id}' IS DISTINCT FROM 'body'
              OR report.structured_values <> '{}'::jsonb
              OR jsonb_typeof(report.content -> 'values') IS DISTINCT FROM 'object'
              OR report.content -> 'values' <> CASE
                  WHEN report.body IS NULL THEN '{}'::jsonb
                  ELSE jsonb_build_object('body', report.body)
              END
          )
    ) OR EXISTS (
        SELECT 1
        FROM public.report_deal AS section
        JOIN public.report AS report ON report.id = section.report_id
        WHERE report.report_kind = 'meeting'
          AND (
              section.structured_values <> '{}'::jsonb
              OR jsonb_typeof(section.content -> 'values') IS DISTINCT FROM 'object'
              OR section.content -> 'values' <> jsonb_build_object('body', section.body)
          )
    ) OR EXISTS (
        SELECT 1
        FROM public.report AS report
        WHERE report.report_kind = 'meeting'
          AND report.sales_deal_id IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'report body migration postcondition failed';
    END IF;
END
$$;

COMMIT;
