BEGIN;

CREATE TABLE public.products (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.teams (id),
    name text NOT NULL CHECK (btrim(name) <> ''),
    active boolean NOT NULL DEFAULT true
);

CREATE INDEX products_team_active_idx
    ON public.products (team_id, active);

CREATE TABLE public.notices (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.teams (id),
    author_member_id uuid NOT NULL REFERENCES public.members (id),
    recipient_member_id uuid REFERENCES public.members (id),
    tag text CHECK (tag IS NULL OR btrim(tag) <> ''),
    title text NOT NULL CHECK (btrim(title) <> ''),
    body text NOT NULL CHECK (btrim(body) <> ''),
    image_storage_key text CHECK (image_storage_key IS NULL OR btrim(image_storage_key) <> ''),
    image_alt text CHECK (image_alt IS NULL OR btrim(image_alt) <> ''),
    published_at timestamptz NOT NULL DEFAULT now(),
    due_at timestamptz,
    due_text text CHECK (due_text IS NULL OR btrim(due_text) <> '')
);

CREATE INDEX notices_team_recipient_published_idx
    ON public.notices (team_id, recipient_member_id, published_at DESC);

CREATE TABLE public.support_requests (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.teams (id),
    customer_contact_id uuid NOT NULL REFERENCES public.customer_contacts (id),
    assignee_member_id uuid NOT NULL REFERENCES public.members (id),
    title text NOT NULL CHECK (btrim(title) <> ''),
    body text NOT NULL CHECK (btrim(body) <> ''),
    is_urgent boolean NOT NULL DEFAULT false,
    status_code text NOT NULL CHECK (btrim(status_code) <> ''),
    registered_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX support_requests_team_assignee_status_idx
    ON public.support_requests (team_id, assignee_member_id, status_code);

CREATE TABLE public.support_responses (
    id uuid PRIMARY KEY,
    request_id uuid NOT NULL REFERENCES public.support_requests (id),
    responder_member_id uuid NOT NULL REFERENCES public.members (id),
    body text NOT NULL CHECK (btrim(body) <> ''),
    responded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX support_responses_request_responded_idx
    ON public.support_responses (request_id, responded_at);

CREATE TABLE public.pipeline_stages (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.teams (id),
    name text NOT NULL CHECK (btrim(name) <> ''),
    tone text NOT NULL CHECK (btrim(tone) <> ''),
    outcome_code text NOT NULL CHECK (outcome_code IN ('in_progress', 'confirmed', 'cancelled')),
    position integer NOT NULL CHECK (position >= 0)
);

CREATE INDEX pipeline_stages_team_position_idx
    ON public.pipeline_stages (team_id, position);

CREATE TABLE public.contracts (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.teams (id),
    contract_no text NOT NULL CHECK (btrim(contract_no) <> ''),
    customer_company_id uuid NOT NULL REFERENCES public.customer_companies (id),
    contact_id uuid REFERENCES public.customer_contacts (id),
    owner_member_id uuid NOT NULL REFERENCES public.members (id),
    product_id uuid REFERENCES public.products (id),
    stage_id uuid NOT NULL REFERENCES public.pipeline_stages (id),
    title text NOT NULL CHECK (btrim(title) <> ''),
    description text CHECK (description IS NULL OR btrim(description) <> ''),
    contract_type text NOT NULL CHECK (btrim(contract_type) <> ''),
    amount bigint NOT NULL CHECK (amount >= 0),
    contract_date date NOT NULL,
    ends_on date,
    warranty_terms text CHECK (warranty_terms IS NULL OR btrim(warranty_terms) <> ''),
    expected_delivery_at timestamptz,
    memo text CHECK (memo IS NULL OR btrim(memo) <> ''),
    position integer NOT NULL CHECK (position >= 0),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX contracts_team_stage_position_idx
    ON public.contracts (team_id, stage_id, position)
    WHERE deleted_at IS NULL;

CREATE INDEX contracts_team_owner_date_idx
    ON public.contracts (team_id, owner_member_id, contract_date)
    WHERE deleted_at IS NULL;

CREATE INDEX contracts_ends_on_idx
    ON public.contracts (ends_on)
    WHERE ends_on IS NOT NULL AND deleted_at IS NULL;

CREATE TABLE public.orders (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.teams (id),
    order_no text NOT NULL CHECK (btrim(order_no) <> ''),
    contract_id uuid REFERENCES public.contracts (id),
    customer_company_id uuid NOT NULL REFERENCES public.customer_companies (id),
    owner_member_id uuid NOT NULL REFERENCES public.members (id),
    supplier_name text NOT NULL CHECK (btrim(supplier_name) <> ''),
    stage_code text NOT NULL CHECK (btrim(stage_code) <> ''),
    ordered_on date NOT NULL,
    due_on date NOT NULL,
    expected_receipt_on date NOT NULL,
    memo text CHECK (memo IS NULL OR btrim(memo) <> ''),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX orders_team_owner_due_idx
    ON public.orders (team_id, owner_member_id, due_on)
    WHERE deleted_at IS NULL;

CREATE INDEX orders_expected_receipt_idx
    ON public.orders (expected_receipt_on)
    WHERE deleted_at IS NULL;

CREATE INDEX orders_contract_idx
    ON public.orders (contract_id)
    WHERE contract_id IS NOT NULL AND deleted_at IS NULL;

CREATE TABLE public.order_items (
    id uuid PRIMARY KEY,
    order_id uuid NOT NULL REFERENCES public.orders (id) ON DELETE CASCADE,
    product_id uuid NOT NULL REFERENCES public.products (id),
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price bigint NOT NULL CHECK (unit_price >= 0),
    position integer NOT NULL CHECK (position >= 0)
);

CREATE INDEX order_items_order_position_idx
    ON public.order_items (order_id, position);

CREATE TABLE public.sales_targets (
    id uuid PRIMARY KEY,
    owner_member_id uuid NOT NULL REFERENCES public.members (id),
    customer_company_id uuid NOT NULL REFERENCES public.customer_companies (id),
    target_month date NOT NULL CHECK (EXTRACT(DAY FROM target_month) = 1),
    target_amount bigint NOT NULL CHECK (target_amount >= 0),
    UNIQUE (owner_member_id, customer_company_id, target_month)
);

CREATE INDEX sales_targets_month_owner_idx
    ON public.sales_targets (target_month, owner_member_id);

ALTER TABLE public.activities
    ADD COLUMN product_id uuid REFERENCES public.products (id),
    ADD COLUMN contract_id uuid REFERENCES public.contracts (id),
    ADD COLUMN order_id uuid REFERENCES public.orders (id);

CREATE INDEX activities_product_idx
    ON public.activities (product_id)
    WHERE product_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX activities_contract_idx
    ON public.activities (contract_id)
    WHERE contract_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX activities_order_idx
    ON public.activities (order_id)
    WHERE order_id IS NOT NULL AND deleted_at IS NULL;

CREATE TABLE public.reports (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.teams (id),
    author_member_id uuid NOT NULL REFERENCES public.members (id),
    recipient_member_id uuid REFERENCES public.members (id),
    template_snapshot jsonb NOT NULL,
    source_activity_id uuid REFERENCES public.activities (id),
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
    reviewed_by_member_id uuid REFERENCES public.members (id),
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT reports_period_order
        CHECK (period_start IS NULL OR period_end IS NULL OR period_end >= period_start)
);

CREATE INDEX reports_team_author_date_idx
    ON public.reports (team_id, author_member_id, report_date DESC);

CREATE INDEX reports_team_status_idx
    ON public.reports (team_id, status_code);

CREATE INDEX reports_source_activity_idx
    ON public.reports (source_activity_id)
    WHERE source_activity_id IS NOT NULL;

CREATE TABLE public.report_activities (
    report_id uuid NOT NULL REFERENCES public.reports (id) ON DELETE CASCADE,
    activity_id uuid NOT NULL REFERENCES public.activities (id),
    PRIMARY KEY (report_id, activity_id)
);

CREATE INDEX report_activities_activity_idx
    ON public.report_activities (activity_id);

CREATE TABLE public.documents (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.teams (id),
    created_by_member_id uuid NOT NULL REFERENCES public.members (id),
    document_no text NOT NULL CHECK (btrim(document_no) <> ''),
    category_code text NOT NULL CHECK (btrim(category_code) <> ''),
    title text NOT NULL CHECK (btrim(title) <> ''),
    description text CHECK (description IS NULL OR btrim(description) <> ''),
    customer_company_id uuid REFERENCES public.customer_companies (id),
    contract_id uuid REFERENCES public.contracts (id),
    order_id uuid REFERENCES public.orders (id),
    tags jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(tags) = 'array'),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX documents_team_created_idx
    ON public.documents (team_id, created_at DESC);

CREATE INDEX documents_customer_company_idx
    ON public.documents (customer_company_id)
    WHERE customer_company_id IS NOT NULL;

CREATE TABLE public.files (
    id uuid PRIMARY KEY,
    report_id uuid REFERENCES public.reports (id),
    document_id uuid REFERENCES public.documents (id),
    version_no integer,
    file_name text NOT NULL CHECK (btrim(file_name) <> ''),
    storage_key text NOT NULL UNIQUE CHECK (btrim(storage_key) <> ''),
    media_type text CHECK (media_type IS NULL OR btrim(media_type) <> ''),
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    processing_status text NOT NULL
        CHECK (processing_status IN ('uploaded', 'processing', 'completed', 'failed')),
    extracted_text text CHECK (extracted_text IS NULL OR btrim(extracted_text) <> ''),
    uploaded_by_member_id uuid NOT NULL REFERENCES public.members (id),
    note text CHECK (note IS NULL OR btrim(note) <> ''),
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT files_exactly_one_parent
        CHECK (num_nonnulls(report_id, document_id) = 1),
    CONSTRAINT files_document_version
        CHECK (
            (document_id IS NOT NULL AND version_no IS NOT NULL AND version_no >= 1)
            OR (report_id IS NOT NULL AND version_no IS NULL)
        ),
    UNIQUE (document_id, version_no)
);

CREATE INDEX files_report_idx
    ON public.files (report_id)
    WHERE report_id IS NOT NULL;

CREATE TABLE public.agent_runs (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.teams (id),
    parent_run_id uuid REFERENCES public.agent_runs (id),
    requested_by_member_id uuid REFERENCES public.members (id),
    agent_code text NOT NULL CHECK (btrim(agent_code) <> ''),
    trigger_code text NOT NULL CHECK (btrim(trigger_code) <> ''),
    idempotency_key uuid,
    status_code text NOT NULL CHECK (status_code IN ('queued', 'running', 'completed', 'failed')),
    model_name text NOT NULL CHECK (btrim(model_name) <> ''),
    prompt_version text NOT NULL CHECK (btrim(prompt_version) <> ''),
    source_refs jsonb NOT NULL,
    input_snapshot jsonb NOT NULL,
    output_snapshot jsonb,
    evidence jsonb,
    error_message text CHECK (error_message IS NULL OR btrim(error_message) <> ''),
    started_at timestamptz,
    finished_at timestamptz,
    CONSTRAINT agent_runs_not_own_parent
        CHECK (parent_run_id IS NULL OR parent_run_id <> id),
    CONSTRAINT agent_runs_idempotency_requester
        CHECK (idempotency_key IS NULL OR requested_by_member_id IS NOT NULL),
    UNIQUE (requested_by_member_id, idempotency_key)
);

CREATE INDEX agent_runs_team_status_idx
    ON public.agent_runs (team_id, status_code);

CREATE INDEX agent_runs_parent_idx
    ON public.agent_runs (parent_run_id)
    WHERE parent_run_id IS NOT NULL;

ALTER TABLE public.teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activity_companions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.support_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.support_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pipeline_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales_targets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.report_activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_runs ENABLE ROW LEVEL SECURITY;

COMMIT;
