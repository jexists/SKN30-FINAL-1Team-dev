-- SalesLuv 최종 스키마 baseline.
--
-- 기존 0001~0007 을 대체한다. 되돌리는 마이그레이션이 아니라 빈 스키마에 처음부터
-- 만드는 파일이므로, 적용 전에 public 스키마의 26테이블을 먼저 지운다.
-- 26테이블 / 264컬럼 / 외래키 65개(public 대상 64개 + member.id -> auth.users 1개).
--
-- 로그인은 Supabase Auth 가 담당한다. member 행 하나가 auth 사용자 하나이며
-- 별도 연결 컬럼 없이 PK 자체를 auth.users.id 로 맞춘다. 따라서 seed 를 돌리기 전에
-- Supabase Dashboard 에 대응하는 사용자가 먼저 있어야 한다.
--
-- 제약조건 이름은 옛 SQL 이 남긴 복수형 흔적(members_pkey 등) 대신 단수 테이블명을
-- 따른다. 다만 app/models/sales.py 가 이름으로 참조하는 네 개는 그대로 유지한다.

BEGIN;

CREATE TABLE public.team (
    id uuid PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name) <> ''),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- 인증은 Supabase 가, 팀·역할·활성 판단은 이 테이블이 담당한다.
CREATE TABLE public.member (
    id uuid PRIMARY KEY REFERENCES auth.users (id),
    team_id uuid NOT NULL REFERENCES public.team (id),
    display_name text NOT NULL CHECK (btrim(display_name) <> ''),
    role_code text NOT NULL CHECK (role_code IN ('member', 'manager')),
    job_title text CHECK (job_title IS NULL OR btrim(job_title) <> ''),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX member_team_active_idx ON public.member (team_id, active);

COMMENT ON COLUMN public.member.id IS
    'auth.users.id 와 같은 값. 인증은 Supabase 가, 팀·역할·활성 판단은 이 테이블이 담당한다.';

CREATE TABLE public.customer_company (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    name text NOT NULL CHECK (btrim(name) <> ''),
    region_code text CHECK (region_code IS NULL OR btrim(region_code) <> ''),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- 아래 유일 인덱스가 같은 컬럼을 덮지만, 기존 스키마에 함께 있던 인덱스라 그대로 옮긴다.
CREATE INDEX customer_company_team_name_idx ON public.customer_company (team_id, name);
CREATE UNIQUE INDEX customer_company_team_name_uq ON public.customer_company (team_id, name);

CREATE TABLE public.customer_contact_status (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    code text NOT NULL CHECK (btrim(code) <> ''),
    name text NOT NULL CHECK (btrim(name) <> ''),
    tone text NOT NULL CHECK (tone IN ('gray', 'blue', 'purple', 'orange', 'green', 'red')),
    "position" integer NOT NULL CHECK ("position" >= 0),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (team_id, code)
);

CREATE INDEX customer_contact_status_team_position_idx
    ON public.customer_contact_status (team_id, "position")
    WHERE deleted_at IS NULL;

CREATE TABLE public.activity_category (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    code text NOT NULL CHECK (btrim(code) <> ''),
    name text NOT NULL CHECK (btrim(name) <> ''),
    tone text NOT NULL CHECK (tone IN ('gray', 'blue', 'purple', 'orange', 'green', 'red')),
    "position" integer NOT NULL CHECK ("position" >= 0),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    activity_type text NOT NULL CHECK (activity_type IN ('meeting', 'task')),
    UNIQUE (team_id, code)
);

CREATE INDEX activity_category_team_position_idx
    ON public.activity_category (team_id, "position")
    WHERE deleted_at IS NULL;

CREATE TABLE public.activity_action_tag (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    code text NOT NULL CHECK (btrim(code) <> ''),
    name text NOT NULL CHECK (btrim(name) <> ''),
    tone text NOT NULL CHECK (tone IN ('gray', 'blue', 'purple', 'orange', 'green', 'red')),
    "position" integer NOT NULL CHECK ("position" >= 0),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    activity_type text NOT NULL CHECK (activity_type IN ('meeting', 'task')),
    UNIQUE (team_id, code)
);

CREATE INDEX activity_action_tag_team_position_idx
    ON public.activity_action_tag (team_id, "position")
    WHERE deleted_at IS NULL;

CREATE TABLE public.sales_deal_type (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    code text NOT NULL CHECK (btrim(code) <> ''),
    name text NOT NULL CHECK (btrim(name) <> ''),
    "position" integer NOT NULL CHECK ("position" >= 0),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (team_id, code)
);

CREATE INDEX sales_deal_type_team_position_idx
    ON public.sales_deal_type (team_id, "position")
    WHERE deleted_at IS NULL;

CREATE TABLE public.purchase_order_status (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    code text NOT NULL CHECK (btrim(code) <> ''),
    name text NOT NULL CHECK (btrim(name) <> ''),
    tone text NOT NULL CHECK (tone IN ('gray', 'blue', 'purple', 'orange', 'green', 'red')),
    "position" integer NOT NULL CHECK ("position" >= 0),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    outcome_code text NOT NULL
        CHECK (outcome_code IN ('in_progress', 'completed', 'cancelled')),
    UNIQUE (team_id, code)
);

CREATE INDEX purchase_order_status_team_position_idx
    ON public.purchase_order_status (team_id, "position")
    WHERE deleted_at IS NULL;

CREATE TABLE public.sales_pipeline (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    name text NOT NULL CHECK (btrim(name) <> ''),
    description text CHECK (description IS NULL OR btrim(description) <> ''),
    status_code text NOT NULL CHECK (status_code IN ('draft', 'published', 'archived')),
    is_default boolean NOT NULL DEFAULT false,
    published_at timestamptz,
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (team_id, name),
    CONSTRAINT sales_pipeline_default_check
        CHECK (NOT is_default OR status_code = 'published'),
    CONSTRAINT sales_pipeline_lifecycle_check CHECK (
        (status_code = 'draft' AND published_at IS NULL AND archived_at IS NULL)
        OR (status_code = 'published' AND published_at IS NOT NULL AND archived_at IS NULL)
        OR (
            status_code = 'archived'
            AND published_at IS NOT NULL
            AND archived_at IS NOT NULL
            AND archived_at >= published_at
        )
    )
);

CREATE UNIQUE INDEX sales_pipeline_team_published_default_uq
    ON public.sales_pipeline (team_id)
    WHERE is_default AND status_code = 'published';

CREATE INDEX sales_pipeline_team_status_idx
    ON public.sales_pipeline (team_id, status_code, created_at DESC);

-- 유일 제약 세 개는 app/models/sales.py 가 이름으로 참조하므로 이름을 바꾸지 않는다.
CREATE TABLE public.sales_pipeline_stage (
    id uuid PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name) <> ''),
    tone text NOT NULL CHECK (tone IN ('gray', 'blue', 'purple', 'orange', 'green', 'red')),
    outcome_code text NOT NULL
        CHECK (outcome_code IN ('in_progress', 'confirmed', 'cancelled')),
    "position" integer NOT NULL CHECK ("position" >= 0),
    sales_pipeline_id uuid NOT NULL REFERENCES public.sales_pipeline (id),
    stage_code text NOT NULL CHECK (btrim(stage_code) <> ''),
    phase_code text NOT NULL
        CHECK (phase_code IN ('sales', 'quote', 'contract', 'order', 'closed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sales_pipeline_stage_sales_pipeline_id_stage_code_key
        UNIQUE (sales_pipeline_id, stage_code),
    CONSTRAINT sales_pipeline_stage_sales_pipeline_id_position_key
        UNIQUE (sales_pipeline_id, "position"),
    CONSTRAINT sales_pipeline_stage_sales_pipeline_id_id_key
        UNIQUE (sales_pipeline_id, id)
);

CREATE TABLE public.product (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    name text NOT NULL CHECK (btrim(name) <> ''),
    active boolean NOT NULL DEFAULT true
);

CREATE INDEX product_team_active_idx ON public.product (team_id, active);

CREATE TABLE public.customer_contact (
    id uuid PRIMARY KEY,
    company_id uuid NOT NULL REFERENCES public.customer_company (id),
    owner_member_id uuid NOT NULL REFERENCES public.member (id),
    name text NOT NULL CHECK (btrim(name) <> ''),
    department text CHECK (department IS NULL OR btrim(department) <> ''),
    job_title text CHECK (job_title IS NULL OR btrim(job_title) <> ''),
    email text CHECK (email IS NULL OR btrim(email) <> ''),
    phone text NOT NULL CHECK (btrim(phone) <> ''),
    source_code text CHECK (source_code IS NULL OR btrim(source_code) <> ''),
    memo text CHECK (memo IS NULL OR btrim(memo) <> ''),
    registered_at timestamptz NOT NULL DEFAULT now(),
    customer_contact_status_id uuid REFERENCES public.customer_contact_status (id)
);

CREATE INDEX customer_contact_company_name_idx
    ON public.customer_contact (company_id, name);
CREATE INDEX customer_contact_owner_idx ON public.customer_contact (owner_member_id);

-- 영업 시작부터 견적·계약·발주까지를 한 행으로 잇는다.
CREATE TABLE public.sales_deal (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    deal_no text NOT NULL CHECK (btrim(deal_no) <> ''),
    customer_company_id uuid NOT NULL REFERENCES public.customer_company (id),
    customer_contact_id uuid REFERENCES public.customer_contact (id),
    owner_member_id uuid NOT NULL REFERENCES public.member (id),
    product_id uuid REFERENCES public.product (id),
    sales_pipeline_stage_id uuid NOT NULL,
    title text NOT NULL CHECK (btrim(title) <> ''),
    description text CHECK (description IS NULL OR btrim(description) <> ''),
    deal_amount bigint NOT NULL CHECK (deal_amount >= 0),
    opened_on date NOT NULL,
    contract_ends_on date,
    warranty_terms text CHECK (warranty_terms IS NULL OR btrim(warranty_terms) <> ''),
    expected_delivery_at timestamptz,
    memo text CHECK (memo IS NULL OR btrim(memo) <> ''),
    stage_position integer NOT NULL CHECK (stage_position >= 0),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    sales_pipeline_id uuid NOT NULL,
    sales_deal_type_id uuid NOT NULL REFERENCES public.sales_deal_type (id),
    closed_on date,
    quote_no text CHECK (quote_no IS NULL OR btrim(quote_no) <> ''),
    quote_issued_on date,
    quote_valid_until date,
    contract_no text CHECK (contract_no IS NULL OR btrim(contract_no) <> ''),
    contract_signed_on date,
    UNIQUE (team_id, deal_no),
    UNIQUE (team_id, quote_no),
    UNIQUE (team_id, contract_no),
    CONSTRAINT sales_deal_closed_on_order_check
        CHECK (closed_on IS NULL OR closed_on >= opened_on),
    CONSTRAINT sales_deal_quote_issued_on_check
        CHECK (quote_issued_on IS NULL OR quote_issued_on >= opened_on),
    CONSTRAINT sales_deal_quote_valid_until_check CHECK (
        quote_valid_until IS NULL
        OR (quote_issued_on IS NOT NULL AND quote_valid_until >= quote_issued_on)
    ),
    CONSTRAINT sales_deal_contract_signed_on_check
        CHECK (contract_signed_on IS NULL OR contract_signed_on >= opened_on),
    CONSTRAINT sales_deal_contract_ends_on_order_check CHECK (
        contract_ends_on IS NULL
        OR (contract_signed_on IS NOT NULL AND contract_ends_on >= contract_signed_on)
    ),
    -- 단계가 딜과 같은 파이프라인에 속하도록 복합 외래키로 묶는다.
    -- 이름은 app/models/sales.py 가 참조하므로 바꾸지 않는다.
    CONSTRAINT sales_deal_sales_pipeline_stage_membership_fkey
        FOREIGN KEY (sales_pipeline_id, sales_pipeline_stage_id)
        REFERENCES public.sales_pipeline_stage (sales_pipeline_id, id)
);

CREATE INDEX sales_deal_team_owner_opened_on_idx
    ON public.sales_deal (team_id, owner_member_id, opened_on)
    WHERE deleted_at IS NULL;

CREATE INDEX sales_deal_team_pipeline_stage_position_idx
    ON public.sales_deal (team_id, sales_pipeline_id, sales_pipeline_stage_id, stage_position)
    WHERE deleted_at IS NULL;

CREATE INDEX sales_deal_contract_ends_on_idx
    ON public.sales_deal (contract_ends_on)
    WHERE contract_ends_on IS NOT NULL AND deleted_at IS NULL;

CREATE TABLE public.purchase_order (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    order_no text NOT NULL CHECK (btrim(order_no) <> ''),
    sales_deal_id uuid NOT NULL REFERENCES public.sales_deal (id),
    supplier_name text NOT NULL CHECK (btrim(supplier_name) <> ''),
    ordered_on date NOT NULL,
    due_on date NOT NULL,
    expected_receipt_on date NOT NULL,
    memo text CHECK (memo IS NULL OR btrim(memo) <> ''),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    purchase_order_status_id uuid NOT NULL REFERENCES public.purchase_order_status (id),
    UNIQUE (team_id, order_no),
    CONSTRAINT purchase_order_due_on_order_check CHECK (due_on >= ordered_on),
    CONSTRAINT purchase_order_expected_receipt_on_order_check
        CHECK (expected_receipt_on >= ordered_on)
);

CREATE INDEX purchase_order_team_due_idx
    ON public.purchase_order (team_id, due_on)
    WHERE deleted_at IS NULL;

CREATE INDEX purchase_order_sales_deal_idx
    ON public.purchase_order (sales_deal_id)
    WHERE deleted_at IS NULL;

CREATE INDEX purchase_order_expected_receipt_idx
    ON public.purchase_order (expected_receipt_on)
    WHERE deleted_at IS NULL;

CREATE TABLE public.purchase_order_item (
    id uuid PRIMARY KEY,
    purchase_order_id uuid NOT NULL
        REFERENCES public.purchase_order (id) ON DELETE CASCADE,
    product_id uuid NOT NULL REFERENCES public.product (id),
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price bigint NOT NULL CHECK (unit_price >= 0),
    "position" integer NOT NULL CHECK ("position" >= 0)
);

CREATE INDEX purchase_order_item_purchase_order_position_idx
    ON public.purchase_order_item (purchase_order_id, "position");

CREATE TABLE public.activity (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    owner_member_id uuid NOT NULL REFERENCES public.member (id),
    customer_contact_id uuid REFERENCES public.customer_contact (id),
    end_user_contact_id uuid REFERENCES public.customer_contact (id),
    activity_type text NOT NULL CHECK (activity_type IN ('meeting', 'task')),
    title text NOT NULL CHECK (btrim(title) <> ''),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz,
    all_day boolean NOT NULL DEFAULT false,
    due_at timestamptz,
    location text CHECK (location IS NULL OR btrim(location) <> ''),
    completed_at timestamptz,
    note text CHECK (note IS NULL OR btrim(note) <> ''),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    product_id uuid REFERENCES public.product (id),
    sales_deal_id uuid REFERENCES public.sales_deal (id),
    purchase_order_id uuid REFERENCES public.purchase_order (id),
    activity_category_id uuid NOT NULL REFERENCES public.activity_category (id),
    activity_action_tag_id uuid REFERENCES public.activity_action_tag (id),
    CONSTRAINT activity_ends_after_start CHECK (ends_at IS NULL OR ends_at > starts_at)
);

CREATE INDEX activity_team_starts_idx
    ON public.activity (team_id, starts_at)
    WHERE deleted_at IS NULL;

CREATE INDEX activity_team_owner_starts_idx
    ON public.activity (team_id, owner_member_id, starts_at)
    WHERE deleted_at IS NULL;

CREATE INDEX activity_customer_contact_idx
    ON public.activity (customer_contact_id)
    WHERE customer_contact_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX activity_product_idx
    ON public.activity (product_id)
    WHERE product_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX activity_sales_deal_idx
    ON public.activity (sales_deal_id)
    WHERE sales_deal_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX activity_purchase_order_idx
    ON public.activity (purchase_order_id)
    WHERE purchase_order_id IS NOT NULL AND deleted_at IS NULL;

CREATE TABLE public.activity_companion (
    activity_id uuid NOT NULL REFERENCES public.activity (id) ON DELETE CASCADE,
    member_id uuid NOT NULL REFERENCES public.member (id),
    PRIMARY KEY (activity_id, member_id)
);

CREATE INDEX activity_companion_member_idx ON public.activity_companion (member_id);

-- 수신자가 없으면 팀 공지, 있으면 개인 지시다.
CREATE TABLE public.notice (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    author_member_id uuid NOT NULL REFERENCES public.member (id),
    recipient_member_id uuid REFERENCES public.member (id),
    tag text CHECK (tag IS NULL OR btrim(tag) <> ''),
    title text NOT NULL CHECK (btrim(title) <> ''),
    body text NOT NULL CHECK (btrim(body) <> ''),
    image_storage_key text
        CHECK (image_storage_key IS NULL OR btrim(image_storage_key) <> ''),
    image_alt text CHECK (image_alt IS NULL OR btrim(image_alt) <> ''),
    published_at timestamptz NOT NULL DEFAULT now(),
    due_at timestamptz,
    due_text text CHECK (due_text IS NULL OR btrim(due_text) <> '')
);

CREATE INDEX notice_team_recipient_published_idx
    ON public.notice (team_id, recipient_member_id, published_at DESC);

CREATE TABLE public.support_request (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    customer_contact_id uuid NOT NULL REFERENCES public.customer_contact (id),
    assignee_member_id uuid NOT NULL REFERENCES public.member (id),
    title text NOT NULL CHECK (btrim(title) <> ''),
    body text NOT NULL CHECK (btrim(body) <> ''),
    is_urgent boolean NOT NULL DEFAULT false,
    status_code text NOT NULL CHECK (btrim(status_code) <> ''),
    registered_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX support_request_team_assignee_status_idx
    ON public.support_request (team_id, assignee_member_id, status_code);

CREATE TABLE public.support_response (
    id uuid PRIMARY KEY,
    support_request_id uuid NOT NULL REFERENCES public.support_request (id),
    responder_member_id uuid NOT NULL REFERENCES public.member (id),
    body text NOT NULL CHECK (btrim(body) <> ''),
    responded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX support_response_support_request_responded_idx
    ON public.support_response (support_request_id, responded_at);

CREATE TABLE public.sales_target (
    id uuid PRIMARY KEY,
    owner_member_id uuid NOT NULL REFERENCES public.member (id),
    customer_company_id uuid NOT NULL REFERENCES public.customer_company (id),
    target_month date NOT NULL CHECK (EXTRACT(day FROM target_month) = 1),
    target_amount bigint NOT NULL CHECK (target_amount >= 0),
    UNIQUE (owner_member_id, customer_company_id, target_month)
);

CREATE INDEX sales_target_month_owner_idx
    ON public.sales_target (target_month, owner_member_id);

CREATE TABLE public.report (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    author_member_id uuid NOT NULL REFERENCES public.member (id),
    recipient_member_id uuid REFERENCES public.member (id),
    template_snapshot jsonb NOT NULL,
    source_activity_id uuid REFERENCES public.activity (id),
    report_kind text NOT NULL CHECK (btrim(report_kind) <> ''),
    report_date date NOT NULL,
    period_start date,
    period_end date,
    status_code text NOT NULL CHECK (btrim(status_code) <> ''),
    content jsonb NOT NULL,
    transcript text CHECK (transcript IS NULL OR btrim(transcript) <> ''),
    source_snapshot jsonb,
    ai_evidence jsonb,
    note text CHECK (note IS NULL OR btrim(note) <> ''),
    reviewed_by_member_id uuid REFERENCES public.member (id),
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT report_period_order CHECK (
        period_start IS NULL OR period_end IS NULL OR period_end >= period_start
    )
);

CREATE INDEX report_team_author_date_idx
    ON public.report (team_id, author_member_id, report_date DESC);

CREATE INDEX report_team_status_idx ON public.report (team_id, status_code);

CREATE INDEX report_source_activity_idx
    ON public.report (source_activity_id)
    WHERE source_activity_id IS NOT NULL;

CREATE TABLE public.report_activity (
    report_id uuid NOT NULL REFERENCES public.report (id) ON DELETE CASCADE,
    activity_id uuid NOT NULL REFERENCES public.activity (id),
    PRIMARY KEY (report_id, activity_id)
);

CREATE INDEX report_activity_activity_idx ON public.report_activity (activity_id);

CREATE TABLE public.document (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    created_by_member_id uuid NOT NULL REFERENCES public.member (id),
    document_no text NOT NULL CHECK (btrim(document_no) <> ''),
    category_code text NOT NULL CHECK (btrim(category_code) <> ''),
    title text NOT NULL CHECK (btrim(title) <> ''),
    description text CHECK (description IS NULL OR btrim(description) <> ''),
    customer_company_id uuid REFERENCES public.customer_company (id),
    sales_deal_id uuid REFERENCES public.sales_deal (id),
    purchase_order_id uuid REFERENCES public.purchase_order (id),
    tags jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(tags) = 'array'),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX document_team_created_idx ON public.document (team_id, created_at DESC);

CREATE INDEX document_customer_company_idx
    ON public.document (customer_company_id)
    WHERE customer_company_id IS NOT NULL;

-- 보고서 첨부이거나 문서 버전이거나, 둘 중 하나에만 속한다.
CREATE TABLE public.file (
    id uuid PRIMARY KEY,
    report_id uuid REFERENCES public.report (id),
    document_id uuid REFERENCES public.document (id),
    version_no integer,
    file_name text NOT NULL CHECK (btrim(file_name) <> ''),
    storage_key text NOT NULL UNIQUE CHECK (btrim(storage_key) <> ''),
    media_type text CHECK (media_type IS NULL OR btrim(media_type) <> ''),
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    processing_status text NOT NULL
        CHECK (processing_status IN ('uploaded', 'processing', 'completed', 'failed')),
    extracted_text text CHECK (extracted_text IS NULL OR btrim(extracted_text) <> ''),
    uploaded_by_member_id uuid NOT NULL REFERENCES public.member (id),
    note text CHECK (note IS NULL OR btrim(note) <> ''),
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, version_no),
    CONSTRAINT file_exactly_one_parent CHECK (num_nonnulls(report_id, document_id) = 1),
    CONSTRAINT file_document_version CHECK (
        (document_id IS NOT NULL AND version_no IS NOT NULL AND version_no >= 1)
        OR (report_id IS NOT NULL AND version_no IS NULL)
    )
);

CREATE INDEX file_report_idx ON public.file (report_id) WHERE report_id IS NOT NULL;

CREATE TABLE public.agent_run (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    parent_run_id uuid REFERENCES public.agent_run (id),
    requested_by_member_id uuid REFERENCES public.member (id),
    agent_code text NOT NULL CHECK (btrim(agent_code) <> ''),
    trigger_code text NOT NULL CHECK (btrim(trigger_code) <> ''),
    idempotency_key uuid,
    status_code text NOT NULL
        CHECK (status_code IN ('queued', 'running', 'completed', 'failed')),
    llm_model_name text NOT NULL CHECK (btrim(llm_model_name) <> ''),
    prompt_version text NOT NULL CHECK (btrim(prompt_version) <> ''),
    source_refs jsonb NOT NULL,
    input_snapshot jsonb NOT NULL,
    output_snapshot jsonb,
    evidence jsonb,
    error_message text CHECK (error_message IS NULL OR btrim(error_message) <> ''),
    started_at timestamptz,
    finished_at timestamptz,
    UNIQUE (requested_by_member_id, idempotency_key),
    CONSTRAINT agent_run_not_own_parent
        CHECK (parent_run_id IS NULL OR parent_run_id <> id),
    CONSTRAINT agent_run_idempotency_requester
        CHECK (idempotency_key IS NULL OR requested_by_member_id IS NOT NULL)
);

CREATE INDEX agent_run_team_status_idx ON public.agent_run (team_id, status_code);

CREATE INDEX agent_run_parent_idx
    ON public.agent_run (parent_run_id)
    WHERE parent_run_id IS NOT NULL;

ALTER TABLE public.team ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.member ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_company ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_contact_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activity_category ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activity_action_tag ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales_deal_type ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.purchase_order_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales_pipeline ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales_pipeline_stage ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_contact ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales_deal ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.purchase_order ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.purchase_order_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activity_companion ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notice ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.support_request ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.support_response ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales_target ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.report ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.report_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.file ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_run ENABLE ROW LEVEL SECURITY;

COMMIT;
