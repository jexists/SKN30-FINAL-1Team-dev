-- 보고서 작업본, 확정본, 출처, 딜별 ML 결과를 서로 다른 수명 주기로 보관한다.
-- 0016의 report 1 : report_deal N 구조와 레거시 JSON 컬럼은 전환 기간 동안 그대로 둔다.
BEGIN;

ALTER TABLE public.report
    ADD COLUMN customer_company_id uuid REFERENCES public.customer_company (id),
    ADD COLUMN title text,
    ADD COLUMN body text,
    ADD COLUMN common_body text,
    ADD COLUMN unassigned_body text,
    ADD COLUMN structured_values jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN version bigint NOT NULL DEFAULT 1,
    ADD COLUMN generation_input_version bigint NOT NULL DEFAULT 1,
    ADD COLUMN last_applied_agent_run_id uuid,
    ADD COLUMN current_submission_id uuid;

ALTER TABLE public.report_deal
    ADD COLUMN position integer,
    ADD COLUMN deal_no_snapshot text,
    ADD COLUMN deal_title_snapshot text,
    ADD COLUMN title text,
    ADD COLUMN body text,
    ADD COLUMN structured_values jsonb NOT NULL DEFAULT '{}'::jsonb;

-- 기존 JSON에서 직접 읽을 수 있는 값만 새 정규화 컬럼으로 옮긴다. 값이 없거나 형식이
-- 손상되었으면 NULL/빈 객체로 두며, 현재 CRM 값을 과거 스냅샷처럼 꾸미지 않는다.
UPDATE public.report
SET title = nullif(btrim(content ->> 'title'), ''),
    body = nullif(btrim(coalesce(content #>> '{values,body}', content ->> 'body')), ''),
    common_body = nullif(btrim(content #>> '{meeting_shared,common_report,body}'), ''),
    unassigned_body = nullif(btrim(content #>> '{meeting_shared,unassigned_report,body}'), ''),
    structured_values = CASE
        WHEN jsonb_typeof(content -> 'values') = 'object' THEN (content -> 'values') - 'body'
        ELSE '{}'::jsonb
    END;

UPDATE public.report_deal
SET deal_no_snapshot = nullif(btrim(deal_snapshot ->> 'label'), ''),
    deal_title_snapshot = nullif(btrim(deal_snapshot ->> 'note'), ''),
    title = nullif(btrim(content ->> 'title'), ''),
    body = nullif(btrim(coalesce(content #>> '{values,body}', content ->> 'body')), ''),
    structured_values = CASE
        WHEN jsonb_typeof(content -> 'values') = 'object' THEN (content -> 'values') - 'body'
        ELSE '{}'::jsonb
    END;

-- 고객사는 선택 딜, 레거시 단일 딜, 미팅 고객 담당자에서 같은 값 하나가 확인될 때만
-- 백필한다. 서로 다른 회사가 나오면 어느 하나도 임의로 고르지 않고 NULL로 남긴다.
WITH company_candidate AS (
    SELECT section.report_id, deal.customer_company_id
    FROM public.report_deal AS section
    JOIN public.sales_deal AS deal ON deal.id = section.sales_deal_id
    UNION
    SELECT report.id, deal.customer_company_id
    FROM public.report AS report
    JOIN public.sales_deal AS deal ON deal.id = report.sales_deal_id
    WHERE report.sales_deal_id IS NOT NULL
    UNION
    SELECT report.id, contact.company_id
    FROM public.report AS report
    JOIN public.activity AS activity ON activity.id = report.source_activity_id
    JOIN public.customer_contact AS contact ON contact.id = activity.customer_contact_id
), one_company AS (
    SELECT report_id, min(customer_company_id::text)::uuid AS customer_company_id
    FROM company_candidate
    GROUP BY report_id
    HAVING count(DISTINCT customer_company_id) = 1
)
UPDATE public.report AS report
SET customer_company_id = one_company.customer_company_id
FROM one_company
WHERE report.id = one_company.report_id;

-- JSON null은 PostgreSQL NULL과 달라 nullable JSONB CHECK를 통과하지 않는다. 기존에
-- 들어온 JSON null을 먼저 정규화하고 이후 바인딩은 ORM의 none_as_null=True가 맡는다.
UPDATE public.report SET source_snapshot = NULL WHERE source_snapshot = 'null'::jsonb;
UPDATE public.report SET ai_evidence = NULL WHERE ai_evidence = 'null'::jsonb;
UPDATE public.report_deal SET ai_evidence = NULL WHERE ai_evidence = 'null'::jsonb;

-- 구 API의 rejected는 현재의 "수정 요청"과 같은 뜻이다. 신규 상태 계약에 맞춰
-- changes_requested로 옮기고 본문은 그대로 둔다.
UPDATE public.report SET status_code = 'changes_requested' WHERE status_code = 'rejected';

ALTER TABLE public.report
    ADD CONSTRAINT report_kind_allowed_check
        CHECK (report_kind IN ('meeting', 'daily', 'weekly', 'monthly')),
    ADD CONSTRAINT report_status_allowed_check
        CHECK (status_code IN ('draft', 'submitted', 'approved', 'changes_requested')),
    ADD CONSTRAINT report_title_nonblank
        CHECK (title IS NULL OR btrim(title) <> ''),
    ADD CONSTRAINT report_common_body_nonblank
        CHECK (common_body IS NULL OR btrim(common_body) <> ''),
    ADD CONSTRAINT report_unassigned_body_nonblank
        CHECK (unassigned_body IS NULL OR btrim(unassigned_body) <> ''),
    ADD CONSTRAINT report_structured_values_object
        CHECK (jsonb_typeof(structured_values) = 'object'),
    ADD CONSTRAINT report_source_snapshot_object
        CHECK (source_snapshot IS NULL OR jsonb_typeof(source_snapshot) = 'object'),
    ADD CONSTRAINT report_ai_evidence_object
        CHECK (ai_evidence IS NULL OR jsonb_typeof(ai_evidence) = 'object'),
    ADD CONSTRAINT report_version_positive
        CHECK (version >= 1),
    ADD CONSTRAINT report_generation_input_version_positive
        CHECK (generation_input_version >= 1),
    ADD CONSTRAINT report_period_shape_check CHECK (
        (report_kind IN ('meeting', 'daily') AND period_start IS NULL AND period_end IS NULL)
        OR
        (report_kind IN ('weekly', 'monthly')
            AND period_start IS NOT NULL
            AND period_end IS NOT NULL
            AND period_end >= period_start)
    );

ALTER TABLE public.report_deal
    ADD CONSTRAINT report_deal_position_nonnegative
        CHECK (position IS NULL OR position >= 0),
    ADD CONSTRAINT report_deal_no_snapshot_nonblank
        CHECK (deal_no_snapshot IS NULL OR btrim(deal_no_snapshot) <> ''),
    ADD CONSTRAINT report_deal_title_snapshot_nonblank
        CHECK (deal_title_snapshot IS NULL OR btrim(deal_title_snapshot) <> ''),
    ADD CONSTRAINT report_deal_title_nonblank
        CHECK (title IS NULL OR btrim(title) <> ''),
    ADD CONSTRAINT report_deal_structured_values_object
        CHECK (jsonb_typeof(structured_values) = 'object');

CREATE INDEX report_team_company_date_idx
    ON public.report (team_id, customer_company_id, report_date DESC)
    WHERE customer_company_id IS NOT NULL;

CREATE INDEX report_last_applied_agent_run_idx
    ON public.report (last_applied_agent_run_id)
    WHERE last_applied_agent_run_id IS NOT NULL;

CREATE UNIQUE INDEX report_deal_position_key
    ON public.report_deal (report_id, position)
    WHERE position IS NOT NULL;

-- 제품 규칙상 한 작성자의 일일/기간 보고서는 같은 기간에 하나다. UNIQUE 생성 자체가
-- 기존 중복을 감사하며, 중복이 있으면 데이터를 고르거나 지우지 않고 migration을 중단한다.
CREATE UNIQUE INDEX report_daily_author_date_key
    ON public.report (team_id, author_member_id, report_date)
    WHERE report_kind = 'daily';

CREATE UNIQUE INDEX report_period_author_range_key
    ON public.report (team_id, author_member_id, report_kind, period_start, period_end)
    WHERE report_kind IN ('weekly', 'monthly');

CREATE TABLE public.report_submission (
    id uuid PRIMARY KEY,
    report_id uuid NOT NULL REFERENCES public.report (id),
    revision_no bigint NOT NULL,
    report_version bigint NOT NULL,
    team_id uuid NOT NULL REFERENCES public.team (id),
    submitted_by_member_id uuid NOT NULL REFERENCES public.member (id),
    snapshot jsonb NOT NULL,
    snapshot_sha256 text NOT NULL,
    review_status text NOT NULL DEFAULT 'pending',
    reviewed_by_member_id uuid REFERENCES public.member (id),
    reviewed_at timestamptz,
    review_note text CHECK (review_note IS NULL OR btrim(review_note) <> ''),
    submitted_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT report_submission_revision_key UNIQUE (report_id, revision_no),
    CONSTRAINT report_submission_report_id_id_key UNIQUE (report_id, id),
    CONSTRAINT report_submission_revision_positive CHECK (revision_no >= 1),
    CONSTRAINT report_submission_report_version_positive CHECK (report_version >= 1),
    CONSTRAINT report_submission_snapshot_object CHECK (jsonb_typeof(snapshot) = 'object'),
    CONSTRAINT report_submission_sha256_check CHECK (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT report_submission_review_status_check
        CHECK (review_status IN ('pending', 'approved', 'changes_requested')),
    CONSTRAINT report_submission_review_state_check CHECK (
        (review_status = 'pending'
            AND reviewed_by_member_id IS NULL
            AND reviewed_at IS NULL
            AND review_note IS NULL)
        OR
        (review_status = 'approved'
            AND reviewed_by_member_id IS NOT NULL
            AND reviewed_at IS NOT NULL)
        OR
        (review_status = 'changes_requested'
            AND reviewed_by_member_id IS NOT NULL
            AND reviewed_at IS NOT NULL
            AND review_note IS NOT NULL)
    )
);

CREATE INDEX report_submission_team_submitted_idx
    ON public.report_submission (team_id, submitted_at DESC);

-- 확정 내용은 수정할 수 없고, pending인 제출본의 검토 결과만 한 번 기록할 수 있다.
CREATE FUNCTION public.guard_report_submission_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF ROW(
        NEW.id,
        NEW.report_id,
        NEW.revision_no,
        NEW.report_version,
        NEW.team_id,
        NEW.submitted_by_member_id,
        NEW.snapshot,
        NEW.snapshot_sha256,
        NEW.submitted_at
    ) IS DISTINCT FROM ROW(
        OLD.id,
        OLD.report_id,
        OLD.revision_no,
        OLD.report_version,
        OLD.team_id,
        OLD.submitted_by_member_id,
        OLD.snapshot,
        OLD.snapshot_sha256,
        OLD.submitted_at
    ) THEN
        RAISE EXCEPTION 'report submission snapshot is immutable';
    END IF;

    IF OLD.review_status <> 'pending'
       AND ROW(NEW.review_status, NEW.reviewed_by_member_id, NEW.reviewed_at, NEW.review_note)
           IS DISTINCT FROM
           ROW(OLD.review_status, OLD.reviewed_by_member_id, OLD.reviewed_at, OLD.review_note)
    THEN
        RAISE EXCEPTION 'report submission review is already final';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER report_submission_update_guard
BEFORE UPDATE ON public.report_submission
FOR EACH ROW EXECUTE FUNCTION public.guard_report_submission_update();

CREATE TABLE public.report_source (
    report_id uuid NOT NULL REFERENCES public.report (id) ON DELETE CASCADE,
    position integer NOT NULL,
    source_activity_id uuid REFERENCES public.activity (id),
    source_report_submission_id uuid REFERENCES public.report_submission (id),
    PRIMARY KEY (report_id, position),
    CONSTRAINT report_source_position_nonnegative CHECK (position >= 0),
    CONSTRAINT report_source_exactly_one_source
        CHECK (num_nonnulls(source_activity_id, source_report_submission_id) = 1)
);

CREATE UNIQUE INDEX report_source_activity_key
    ON public.report_source (report_id, source_activity_id)
    WHERE source_activity_id IS NOT NULL;

CREATE UNIQUE INDEX report_source_submission_key
    ON public.report_source (report_id, source_report_submission_id)
    WHERE source_report_submission_id IS NOT NULL;

CREATE TABLE public.meeting_deal_analysis (
    agent_run_id uuid NOT NULL REFERENCES public.agent_run (id) ON DELETE CASCADE,
    sales_deal_id uuid NOT NULL,
    report_id uuid NOT NULL REFERENCES public.report (id) ON DELETE CASCADE,
    feature_schema_version text NOT NULL CHECK (btrim(feature_schema_version) <> ''),
    features jsonb,
    prediction_label text CHECK (prediction_label IS NULL OR btrim(prediction_label) <> ''),
    probability double precision,
    model_version text CHECK (model_version IS NULL OR btrim(model_version) <> ''),
    error_code text CHECK (error_code IS NULL OR btrim(error_code) <> ''),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (agent_run_id, sales_deal_id),
    CONSTRAINT meeting_deal_analysis_features_object
        CHECK (features IS NULL OR jsonb_typeof(features) = 'object'),
    CONSTRAINT meeting_deal_analysis_probability_check
        CHECK (probability IS NULL OR probability BETWEEN 0 AND 1),
    CONSTRAINT meeting_deal_analysis_result_check CHECK (
        (error_code IS NULL
            AND features IS NOT NULL
            AND num_nonnulls(prediction_label, probability, model_version) = 3)
        OR
        (error_code IS NOT NULL
            AND prediction_label IS NULL
            AND probability IS NULL)
    )
);

CREATE INDEX meeting_deal_analysis_report_deal_idx
    ON public.meeting_deal_analysis (report_id, sales_deal_id, created_at DESC);

-- 두 참조는 각각 이미 만들어진 표를 가리키며 current_submission은 같은 report의
-- 확정본만 선택할 수 있도록 복합 FK로 묶는다.
ALTER TABLE public.report
    ADD CONSTRAINT report_last_applied_agent_run_fkey
        FOREIGN KEY (last_applied_agent_run_id)
        REFERENCES public.agent_run (id)
        ON DELETE SET NULL,
    ADD CONSTRAINT report_current_submission_fkey
        FOREIGN KEY (id, current_submission_id)
        REFERENCES public.report_submission (report_id, id)
        DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE public.report_submission ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.report_source ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.meeting_deal_analysis ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.report_submission IS
    '작성자가 확정한 보고서 불변 스냅샷. 검토 결과만 pending에서 한 번 갱신한다.';
COMMENT ON TABLE public.report_source IS
    '기간 보고서가 실제로 사용한 확정 보고서 또는 활동 출처.';
COMMENT ON TABLE public.meeting_deal_analysis IS
    '에이전트 실행별 딜 13개 특성과 ML 판정. 작업본 딜 섹션을 지워도 이력은 보존한다.';
COMMENT ON COLUMN public.report_deal.position IS
    '신규 딜 표시 순서. 순서를 복원할 근거가 없는 레거시 행은 NULL이다.';

-- 기존 submitted/approved는 SQL 직렬화로 가짜 SHA를 만들지 않는다. current_submission_id가
-- 비어 있으면 백엔드가 잠긴 현재 본문을 Python canonical JSON으로 한 번만 스냅샷한다.
COMMIT;
