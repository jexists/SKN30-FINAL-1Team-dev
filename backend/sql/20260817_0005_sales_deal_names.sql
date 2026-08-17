BEGIN;

-- 관계가 불명확한 기존 행은 임의로 추정하지 않고 트랜잭션 전체를 중단한다.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.contract
        GROUP BY team_id, contract_no HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION
            'sales deal migration blocked: duplicate (team_id, contract_no) values exist';
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.purchase_order
        GROUP BY team_id, order_no HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION
            'sales deal migration blocked: duplicate (team_id, order_no) values exist';
    END IF;

    IF EXISTS (SELECT 1 FROM public.purchase_order WHERE contract_id IS NULL) THEN
        RAISE EXCEPTION
            'sales deal migration blocked: purchase_order.contract_id contains NULL';
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.purchase_order
        WHERE stage_code NOT IN (
            'order_received', 'dispatch_request_completed', 'in_production',
            'stock_received', 'delivered', 'cancelled'
        )
    ) THEN
        RAISE EXCEPTION
            'sales deal migration blocked: unknown purchase_order.stage_code exists';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.purchase_order AS purchase_order
        JOIN public.contract AS contract ON contract.id = purchase_order.contract_id
        WHERE purchase_order.team_id IS DISTINCT FROM contract.team_id
           OR purchase_order.customer_company_id IS DISTINCT FROM contract.customer_company_id
           OR purchase_order.owner_member_id IS DISTINCT FROM contract.owner_member_id
    ) THEN
        RAISE EXCEPTION
            'sales deal migration blocked: purchase order and deal team/company/owner mismatch';
    END IF;

    IF EXISTS (
        WITH expected(id, team_id, name, outcome_code) AS (
            VALUES
                ('1bf0bd69-0925-5ed4-9243-b3e383d0aa9e'::uuid,
                 '6d0f1b76-6b1a-4b72-9ba3-1df477a62d78'::uuid,
                 '니즈 검증'::text, 'in_progress'::text),
                ('7bcd3adb-91ca-5e21-b616-cfeb480d128b'::uuid,
                 '6d0f1b76-6b1a-4b72-9ba3-1df477a62d78'::uuid,
                 '제품 시연 평가'::text, 'in_progress'::text),
                ('6dc01f14-fc7a-5c72-97e4-7484e019c9b5'::uuid,
                 '6d0f1b76-6b1a-4b72-9ba3-1df477a62d78'::uuid,
                 '견적서 발송'::text, 'in_progress'::text),
                ('fce85c11-6f8c-5d7e-a3f1-9d091d4d7028'::uuid,
                 '6d0f1b76-6b1a-4b72-9ba3-1df477a62d78'::uuid,
                 '계약서 발송'::text, 'in_progress'::text),
                ('77d6edeb-cfdd-5349-8629-4ec1846ecc91'::uuid,
                 '6d0f1b76-6b1a-4b72-9ba3-1df477a62d78'::uuid,
                 '계약서 검토'::text, 'in_progress'::text),
                ('0b7a2440-e322-5c95-bdf6-c750c43c9d01'::uuid,
                 '6d0f1b76-6b1a-4b72-9ba3-1df477a62d78'::uuid,
                 '계약 완료'::text, 'confirmed'::text),
                ('680de263-daae-5082-b99c-603d69f0ea68'::uuid,
                 '6d0f1b76-6b1a-4b72-9ba3-1df477a62d78'::uuid,
                 '납품 완료'::text, 'confirmed'::text),
                ('66fada17-627d-5daf-8312-4e57d467e039'::uuid,
                 '6d0f1b76-6b1a-4b72-9ba3-1df477a62d78'::uuid,
                 '취소'::text, 'cancelled'::text)
        )
        SELECT 1
        FROM public.pipeline_stage AS stage
        LEFT JOIN expected ON expected.id = stage.id
        WHERE expected.id IS NULL
           OR stage.team_id IS DISTINCT FROM expected.team_id
           OR stage.name IS DISTINCT FROM expected.name
           OR stage.outcome_code IS DISTINCT FROM expected.outcome_code
    ) THEN
        RAISE EXCEPTION
            'sales pipeline migration blocked: unknown or modified legacy stage exists';
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.activity
        GROUP BY team_id, category_code
        HAVING count(DISTINCT activity_type) > 1
    ) THEN
        RAISE EXCEPTION
            'activity migration blocked: one category_code has multiple activity_type values';
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.activity
        GROUP BY team_id, action_tag
        HAVING action_tag IS NOT NULL AND count(DISTINCT activity_type) > 1
    ) THEN
        RAISE EXCEPTION
            'activity migration blocked: one action_tag has multiple activity_type values';
    END IF;

    IF EXISTS (
        WITH expected(code, activity_type) AS (
            VALUES
                ('visit'::text, 'meeting'::text), ('demo'::text, 'meeting'::text),
                ('education'::text, 'meeting'::text), ('call'::text, 'meeting'::text),
                ('delivery'::text, 'meeting'::text), ('conference'::text, 'meeting'::text),
                ('internal'::text, 'task'::text)
        )
        SELECT 1
        FROM public.activity AS activity
        JOIN expected ON expected.code = activity.category_code
        WHERE activity.activity_type <> expected.activity_type
    ) THEN
        RAISE EXCEPTION
            'activity migration blocked: default category activity_type mismatch';
    END IF;

    IF EXISTS (
        WITH expected(code, activity_type) AS (
            VALUES
                ('first_call'::text, 'meeting'::text), ('meeting'::text, 'meeting'::text),
                ('demo_requested'::text, 'meeting'::text),
                ('demo_in_progress'::text, 'meeting'::text),
                ('demo_completed'::text, 'meeting'::text),
                ('quote_completed'::text, 'meeting'::text),
                ('contract_completed'::text, 'meeting'::text),
                ('product_training'::text, 'meeting'::text),
                ('delivery_completed'::text, 'meeting'::text),
                ('internal_meeting'::text, 'meeting'::text),
                ('conference'::text, 'meeting'::text),
                ('weekly_review'::text, 'task'::text),
                ('monthly_review'::text, 'task'::text),
                ('quarterly_review'::text, 'task'::text), ('ojt'::text, 'task'::text)
        )
        SELECT 1
        FROM public.activity AS activity
        JOIN expected ON expected.code = activity.action_tag
        WHERE activity.activity_type <> expected.activity_type
    ) THEN
        RAISE EXCEPTION
            'activity migration blocked: default action tag activity_type mismatch';
    END IF;
END
$$;

CREATE TABLE public.customer_contact_status (
    id uuid CONSTRAINT customer_contact_status_pkey PRIMARY KEY,
    team_id uuid NOT NULL
        CONSTRAINT customer_contact_status_team_id_fkey REFERENCES public.team (id),
    code text NOT NULL CONSTRAINT customer_contact_status_code_check CHECK (btrim(code) <> ''),
    name text NOT NULL CONSTRAINT customer_contact_status_name_check CHECK (btrim(name) <> ''),
    tone text NOT NULL CONSTRAINT customer_contact_status_tone_check
        CHECK (tone IN ('gray', 'blue', 'purple', 'orange', 'green', 'red')),
    position integer NOT NULL CONSTRAINT customer_contact_status_position_check
        CHECK (position >= 0),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT customer_contact_status_team_id_code_key UNIQUE (team_id, code)
);

CREATE INDEX customer_contact_status_team_position_idx
    ON public.customer_contact_status (team_id, position) WHERE deleted_at IS NULL;

CREATE TABLE public.activity_category (
    id uuid CONSTRAINT activity_category_pkey PRIMARY KEY,
    team_id uuid NOT NULL
        CONSTRAINT activity_category_team_id_fkey REFERENCES public.team (id),
    code text NOT NULL CONSTRAINT activity_category_code_check CHECK (btrim(code) <> ''),
    name text NOT NULL CONSTRAINT activity_category_name_check CHECK (btrim(name) <> ''),
    tone text NOT NULL CONSTRAINT activity_category_tone_check
        CHECK (tone IN ('gray', 'blue', 'purple', 'orange', 'green', 'red')),
    position integer NOT NULL CONSTRAINT activity_category_position_check CHECK (position >= 0),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    activity_type text NOT NULL CONSTRAINT activity_category_activity_type_check
        CHECK (activity_type IN ('meeting', 'task')),
    CONSTRAINT activity_category_team_id_code_key UNIQUE (team_id, code)
);

CREATE INDEX activity_category_team_position_idx
    ON public.activity_category (team_id, position) WHERE deleted_at IS NULL;

CREATE TABLE public.activity_action_tag (
    id uuid CONSTRAINT activity_action_tag_pkey PRIMARY KEY,
    team_id uuid NOT NULL
        CONSTRAINT activity_action_tag_team_id_fkey REFERENCES public.team (id),
    code text NOT NULL CONSTRAINT activity_action_tag_code_check CHECK (btrim(code) <> ''),
    name text NOT NULL CONSTRAINT activity_action_tag_name_check CHECK (btrim(name) <> ''),
    tone text NOT NULL CONSTRAINT activity_action_tag_tone_check
        CHECK (tone IN ('gray', 'blue', 'purple', 'orange', 'green', 'red')),
    position integer NOT NULL CONSTRAINT activity_action_tag_position_check CHECK (position >= 0),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    activity_type text NOT NULL CONSTRAINT activity_action_tag_activity_type_check
        CHECK (activity_type IN ('meeting', 'task')),
    CONSTRAINT activity_action_tag_team_id_code_key UNIQUE (team_id, code)
);

CREATE INDEX activity_action_tag_team_position_idx
    ON public.activity_action_tag (team_id, position) WHERE deleted_at IS NULL;

CREATE TABLE public.sales_deal_type (
    id uuid CONSTRAINT sales_deal_type_pkey PRIMARY KEY,
    team_id uuid NOT NULL CONSTRAINT sales_deal_type_team_id_fkey REFERENCES public.team (id),
    code text NOT NULL CONSTRAINT sales_deal_type_code_check CHECK (btrim(code) <> ''),
    name text NOT NULL CONSTRAINT sales_deal_type_name_check CHECK (btrim(name) <> ''),
    position integer NOT NULL CONSTRAINT sales_deal_type_position_check CHECK (position >= 0),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sales_deal_type_team_id_code_key UNIQUE (team_id, code)
);

CREATE INDEX sales_deal_type_team_position_idx
    ON public.sales_deal_type (team_id, position) WHERE deleted_at IS NULL;

CREATE TABLE public.purchase_order_status (
    id uuid CONSTRAINT purchase_order_status_pkey PRIMARY KEY,
    team_id uuid NOT NULL
        CONSTRAINT purchase_order_status_team_id_fkey REFERENCES public.team (id),
    code text NOT NULL CONSTRAINT purchase_order_status_code_check CHECK (btrim(code) <> ''),
    name text NOT NULL CONSTRAINT purchase_order_status_name_check CHECK (btrim(name) <> ''),
    tone text NOT NULL CONSTRAINT purchase_order_status_tone_check
        CHECK (tone IN ('gray', 'blue', 'purple', 'orange', 'green', 'red')),
    position integer NOT NULL CONSTRAINT purchase_order_status_position_check CHECK (position >= 0),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    outcome_code text NOT NULL CONSTRAINT purchase_order_status_outcome_code_check
        CHECK (outcome_code IN ('in_progress', 'completed', 'cancelled')),
    CONSTRAINT purchase_order_status_team_id_code_key UNIQUE (team_id, code)
);

CREATE INDEX purchase_order_status_team_position_idx
    ON public.purchase_order_status (team_id, position) WHERE deleted_at IS NULL;

CREATE TABLE public.sales_pipeline (
    id uuid CONSTRAINT sales_pipeline_pkey PRIMARY KEY,
    team_id uuid NOT NULL CONSTRAINT sales_pipeline_team_id_fkey REFERENCES public.team (id),
    name text NOT NULL CONSTRAINT sales_pipeline_name_check CHECK (btrim(name) <> ''),
    description text CONSTRAINT sales_pipeline_description_check
        CHECK (description IS NULL OR btrim(description) <> ''),
    status_code text NOT NULL CONSTRAINT sales_pipeline_status_code_check
        CHECK (status_code IN ('draft', 'published', 'archived')),
    is_default boolean NOT NULL DEFAULT false,
    published_at timestamptz,
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sales_pipeline_lifecycle_check CHECK (
        (status_code = 'draft' AND published_at IS NULL AND archived_at IS NULL)
        OR (status_code = 'published' AND published_at IS NOT NULL AND archived_at IS NULL)
        OR (status_code = 'archived' AND published_at IS NOT NULL
            AND archived_at IS NOT NULL AND archived_at >= published_at)
    ),
    CONSTRAINT sales_pipeline_default_check CHECK (NOT is_default OR status_code = 'published')
    ,CONSTRAINT sales_pipeline_team_id_name_key UNIQUE (team_id, name)
);

CREATE UNIQUE INDEX sales_pipeline_team_published_default_uq
    ON public.sales_pipeline (team_id)
    WHERE is_default AND status_code = 'published';

CREATE INDEX sales_pipeline_team_status_idx
    ON public.sales_pipeline (team_id, status_code, created_at DESC);

ALTER TABLE public.customer_contact_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activity_category ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activity_action_tag ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales_deal_type ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.purchase_order_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales_pipeline ENABLE ROW LEVEL SECURITY;

INSERT INTO public.customer_contact_status (
    id, team_id, code, name, tone, position, deleted_at, created_at, updated_at
)
SELECT
    md5(team.id::text || ':customer_contact_status:' || value.code)::uuid,
    team.id, value.code, value.name, value.tone, value.position, NULL, now(), now()
FROM public.team AS team
CROSS JOIN (
    VALUES
        ('new'::text, '신규'::text, 'gray'::text, 0),
        ('proposal'::text, '제안'::text, 'blue'::text, 1),
        ('negotiation'::text, '협의'::text, 'orange'::text, 2),
        ('contracted'::text, '계약'::text, 'green'::text, 3),
        ('on_hold'::text, '보류'::text, 'red'::text, 4)
) AS value(code, name, tone, position);

INSERT INTO public.activity_category (
    id, team_id, code, name, tone, position, deleted_at, created_at, updated_at, activity_type
)
SELECT
    md5(team.id::text || ':activity_category:' || value.code)::uuid,
    team.id, value.code, value.name, value.tone, value.position, NULL, now(), now(),
    value.activity_type
FROM public.team AS team
CROSS JOIN (
    VALUES
        ('visit'::text, '방문'::text, 'blue'::text, 0, 'meeting'::text),
        ('demo'::text, '데모'::text, 'purple'::text, 1, 'meeting'::text),
        ('education'::text, '교육'::text, 'green'::text, 2, 'meeting'::text),
        ('call'::text, '전화'::text, 'gray'::text, 3, 'meeting'::text),
        ('delivery'::text, '납품'::text, 'orange'::text, 4, 'meeting'::text),
        ('conference'::text, '컨퍼런스'::text, 'purple'::text, 5, 'meeting'::text),
        ('internal'::text, '내부업무'::text, 'gray'::text, 6, 'task'::text)
) AS value(code, name, tone, position, activity_type);

INSERT INTO public.activity_action_tag (
    id, team_id, code, name, tone, position, deleted_at, created_at, updated_at, activity_type
)
SELECT
    md5(team.id::text || ':activity_action_tag:' || value.code)::uuid,
    team.id, value.code, value.name, value.tone, value.position, NULL, now(), now(),
    value.activity_type
FROM public.team AS team
CROSS JOIN (
    VALUES
        ('first_call'::text, '첫 전화'::text, 'gray'::text, 0, 'meeting'::text),
        ('meeting'::text, '미팅'::text, 'blue'::text, 1, 'meeting'::text),
        ('demo_requested'::text, '데모 요청'::text, 'blue'::text, 2, 'meeting'::text),
        ('demo_in_progress'::text, '데모 진행'::text, 'purple'::text, 3, 'meeting'::text),
        ('demo_completed'::text, '데모 완료'::text, 'green'::text, 4, 'meeting'::text),
        ('quote_completed'::text, '견적완료'::text, 'purple'::text, 5, 'meeting'::text),
        ('contract_completed'::text, '계약완료'::text, 'green'::text, 6, 'meeting'::text),
        ('product_training'::text, '제품교육'::text, 'blue'::text, 7, 'meeting'::text),
        ('delivery_completed'::text, '납품완료'::text, 'green'::text, 8, 'meeting'::text),
        ('internal_meeting'::text, '내부회의'::text, 'gray'::text, 9, 'meeting'::text),
        ('weekly_review'::text, '주간점검'::text, 'gray'::text, 10, 'task'::text),
        ('monthly_review'::text, '월간점검'::text, 'gray'::text, 11, 'task'::text),
        ('quarterly_review'::text, '분기점검'::text, 'gray'::text, 12, 'task'::text),
        ('conference'::text, '컨퍼런스'::text, 'purple'::text, 13, 'meeting'::text),
        ('ojt'::text, 'OJT'::text, 'blue'::text, 14, 'task'::text)
) AS value(code, name, tone, position, activity_type);

INSERT INTO public.sales_deal_type (
    id, team_id, code, name, position, deleted_at, created_at, updated_at
)
SELECT
    md5(team.id::text || ':sales_deal_type:' || value.code)::uuid,
    team.id, value.code, value.name, value.position, NULL, now(), now()
FROM public.team AS team
CROSS JOIN (
    VALUES
        ('new_installation'::text, '신규 도입'::text, 0),
        ('expansion'::text, '증설'::text, 1),
        ('renewal'::text, '갱신'::text, 2),
        ('maintenance'::text, '유지보수'::text, 3),
        ('consumables_supply'::text, '소모품 공급'::text, 4)
) AS value(code, name, position);

INSERT INTO public.purchase_order_status (
    id, team_id, code, name, tone, position, deleted_at, created_at, updated_at, outcome_code
)
SELECT
    md5(team.id::text || ':purchase_order_status:' || value.code)::uuid,
    team.id, value.code, value.name, value.tone, value.position, NULL, now(), now(),
    value.outcome_code
FROM public.team AS team
CROSS JOIN (
    VALUES
        ('order_received'::text, '발주 접수'::text, 'gray'::text, 0, 'in_progress'::text),
        ('dispatch_request_completed'::text, '출고 의뢰서 완료'::text,
         'purple'::text, 1, 'in_progress'::text),
        ('in_production'::text, '생산중'::text, 'orange'::text, 2, 'in_progress'::text),
        ('stock_received'::text, '입고 완료'::text, 'blue'::text, 3, 'in_progress'::text),
        ('delivered'::text, '납품 완료'::text, 'green'::text, 4, 'completed'::text),
        ('cancelled'::text, '취소'::text, 'red'::text, 5, 'cancelled'::text)
) AS value(code, name, tone, position, outcome_code);

-- 기본값 밖의 기존 자유 텍스트도 팀 설정 행으로 승격해 원래 code를 보존한다.
WITH legacy AS (
    SELECT DISTINCT company.team_id, contact.status_code AS code
    FROM public.customer_contact AS contact
    JOIN public.customer_company AS company ON company.id = contact.company_id
    WHERE contact.status_code IS NOT NULL
), ranked AS (
    SELECT legacy.*,
           row_number() OVER (PARTITION BY team_id ORDER BY code) - 1 AS legacy_position
    FROM legacy
    WHERE NOT EXISTS (
        SELECT 1 FROM public.customer_contact_status AS status
        WHERE status.team_id = legacy.team_id AND status.code = legacy.code
    )
)
INSERT INTO public.customer_contact_status (
    id, team_id, code, name, tone, position, deleted_at, created_at, updated_at
)
SELECT md5(team_id::text || ':customer_contact_status:' || code)::uuid,
       team_id, code, code, 'gray', (5 + legacy_position)::integer, NULL, now(), now()
FROM ranked;

WITH legacy AS (
    SELECT DISTINCT team_id, category_code AS code, activity_type FROM public.activity
), ranked AS (
    SELECT legacy.*,
           row_number() OVER (PARTITION BY team_id ORDER BY code) - 1 AS legacy_position
    FROM legacy
    WHERE NOT EXISTS (
        SELECT 1 FROM public.activity_category AS category
        WHERE category.team_id = legacy.team_id AND category.code = legacy.code
    )
)
INSERT INTO public.activity_category (
    id, team_id, code, name, tone, position, deleted_at, created_at, updated_at, activity_type
)
SELECT md5(team_id::text || ':activity_category:' || code)::uuid,
       team_id, code, code, 'gray', (7 + legacy_position)::integer, NULL, now(), now(),
       activity_type
FROM ranked;

WITH legacy AS (
    SELECT DISTINCT team_id, action_tag AS code, activity_type
    FROM public.activity WHERE action_tag IS NOT NULL
), ranked AS (
    SELECT legacy.*,
           row_number() OVER (PARTITION BY team_id ORDER BY code) - 1 AS legacy_position
    FROM legacy
    WHERE NOT EXISTS (
        SELECT 1 FROM public.activity_action_tag AS action_tag
        WHERE action_tag.team_id = legacy.team_id AND action_tag.code = legacy.code
    )
)
INSERT INTO public.activity_action_tag (
    id, team_id, code, name, tone, position, deleted_at, created_at, updated_at, activity_type
)
SELECT md5(team_id::text || ':activity_action_tag:' || code)::uuid,
       team_id, code, code, 'gray', (15 + legacy_position)::integer, NULL, now(), now(),
       activity_type
FROM ranked;

WITH legacy AS (
    SELECT DISTINCT team_id, contract_type AS code FROM public.contract
), ranked AS (
    SELECT legacy.*,
           row_number() OVER (PARTITION BY team_id ORDER BY code) - 1 AS legacy_position
    FROM legacy
    WHERE NOT EXISTS (
        SELECT 1 FROM public.sales_deal_type AS deal_type
        WHERE deal_type.team_id = legacy.team_id AND deal_type.code = legacy.code
    )
)
INSERT INTO public.sales_deal_type (
    id, team_id, code, name, position, deleted_at, created_at, updated_at
)
SELECT md5(team_id::text || ':sales_deal_type:' || code)::uuid,
       team_id, code, code, (5 + legacy_position)::integer, NULL, now(), now()
FROM ranked;

ALTER TABLE public.customer_contact ADD COLUMN customer_contact_status_id uuid;

UPDATE public.customer_contact AS contact
SET customer_contact_status_id = status.id
FROM public.customer_company AS company,
     public.customer_contact_status AS status
WHERE company.id = contact.company_id
  AND status.team_id = company.team_id
  AND status.code = contact.status_code;

ALTER TABLE public.customer_contact
    DROP COLUMN status_code,
    ADD CONSTRAINT customer_contact_customer_contact_status_id_fkey
        FOREIGN KEY (customer_contact_status_id) REFERENCES public.customer_contact_status (id);

ALTER TABLE public.activity
    ADD COLUMN activity_category_id uuid,
    ADD COLUMN activity_action_tag_id uuid;

UPDATE public.activity AS activity
SET activity_category_id = category.id
FROM public.activity_category AS category
WHERE category.team_id = activity.team_id AND category.code = activity.category_code;

UPDATE public.activity AS activity
SET activity_action_tag_id = action_tag.id
FROM public.activity_action_tag AS action_tag
WHERE action_tag.team_id = activity.team_id AND action_tag.code = activity.action_tag;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.activity
        WHERE activity_category_id IS NULL
           OR (action_tag IS NOT NULL AND activity_action_tag_id IS NULL)
    ) THEN
        RAISE EXCEPTION 'activity migration blocked: lookup backfill failed';
    END IF;
END
$$;

ALTER TABLE public.activity
    ALTER COLUMN activity_category_id SET NOT NULL,
    DROP COLUMN category_code,
    DROP COLUMN action_tag,
    ADD CONSTRAINT activity_activity_category_id_fkey
        FOREIGN KEY (activity_category_id) REFERENCES public.activity_category (id),
    ADD CONSTRAINT activity_activity_action_tag_id_fkey
        FOREIGN KEY (activity_action_tag_id) REFERENCES public.activity_action_tag (id);

INSERT INTO public.sales_pipeline (
    id, team_id, name, description, status_code, is_default,
    published_at, archived_at, created_at, updated_at
)
SELECT md5(team.id::text || ':sales_pipeline:default')::uuid,
       team.id, '기본 영업', NULL, 'published', true, now(), NULL, now(), now()
FROM public.team AS team;

ALTER TABLE public.pipeline_stage RENAME TO sales_pipeline_stage;

ALTER TABLE public.sales_pipeline_stage
    ADD COLUMN sales_pipeline_id uuid,
    ADD COLUMN stage_code text,
    ADD COLUMN phase_code text,
    ADD COLUMN created_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();

UPDATE public.sales_pipeline_stage AS stage
SET sales_pipeline_id = pipeline.id
FROM public.sales_pipeline AS pipeline
WHERE pipeline.team_id = stage.team_id AND pipeline.is_default;

UPDATE public.sales_pipeline_stage AS stage
SET stage_code = expected.stage_code,
    phase_code = expected.phase_code,
    position = expected.position
FROM (
    VALUES
        ('1bf0bd69-0925-5ed4-9243-b3e383d0aa9e'::uuid,
         'needs_validation'::text, 'sales'::text, 0),
        ('7bcd3adb-91ca-5e21-b616-cfeb480d128b'::uuid,
         'product_demo'::text, 'sales'::text, 1),
        ('6dc01f14-fc7a-5c72-97e4-7484e019c9b5'::uuid,
         'quote_sent'::text, 'quote'::text, 2),
        ('fce85c11-6f8c-5d7e-a3f1-9d091d4d7028'::uuid,
         'contract_sent'::text, 'contract'::text, 3),
        ('77d6edeb-cfdd-5349-8629-4ec1846ecc91'::uuid,
         'contract_review'::text, 'contract'::text, 4),
        ('0b7a2440-e322-5c95-bdf6-c750c43c9d01'::uuid,
         'contract_completed'::text, 'contract'::text, 5),
        ('680de263-daae-5082-b99c-603d69f0ea68'::uuid,
         'order_delivered'::text, 'order'::text, 7),
        ('66fada17-627d-5daf-8312-4e57d467e039'::uuid,
         'closed_cancelled'::text, 'closed'::text, 8)
) AS expected(id, stage_code, phase_code, position)
WHERE expected.id = stage.id;

INSERT INTO public.sales_pipeline_stage (
    id, team_id, sales_pipeline_id, stage_code, name, tone, phase_code,
    outcome_code, position, created_at, updated_at
)
SELECT md5(pipeline.id::text || ':sales_pipeline_stage:' || value.stage_code)::uuid,
       pipeline.team_id, pipeline.id, value.stage_code, value.name, value.tone, value.phase_code,
       value.outcome_code, value.position, now(), now()
FROM public.sales_pipeline AS pipeline
CROSS JOIN (
    VALUES
        ('needs_validation'::text, '니즈 검증'::text, 'gray'::text,
         'sales'::text, 'in_progress'::text, 0),
        ('product_demo'::text, '제품 시연 평가'::text, 'blue'::text,
         'sales'::text, 'in_progress'::text, 1),
        ('quote_sent'::text, '견적서 발송'::text, 'purple'::text,
         'quote'::text, 'in_progress'::text, 2),
        ('contract_sent'::text, '계약서 발송'::text, 'orange'::text,
         'contract'::text, 'in_progress'::text, 3),
        ('contract_review'::text, '계약서 검토'::text, 'orange'::text,
         'contract'::text, 'in_progress'::text, 4),
        ('contract_completed'::text, '계약 완료'::text, 'green'::text,
         'contract'::text, 'confirmed'::text, 5),
        ('order_in_progress'::text, '발주 진행'::text, 'purple'::text,
         'order'::text, 'confirmed'::text, 6),
        ('order_delivered'::text, '납품 완료'::text, 'green'::text,
         'order'::text, 'confirmed'::text, 7),
        ('closed_cancelled'::text, '취소'::text, 'red'::text,
         'closed'::text, 'cancelled'::text, 8)
) AS value(stage_code, name, tone, phase_code, outcome_code, position)
WHERE NOT EXISTS (
    SELECT 1 FROM public.sales_pipeline_stage AS stage
    WHERE stage.sales_pipeline_id = pipeline.id AND stage.stage_code = value.stage_code
);

DROP INDEX public.pipeline_stages_team_position_idx;

ALTER TABLE public.sales_pipeline_stage
    ALTER COLUMN sales_pipeline_id SET NOT NULL,
    ALTER COLUMN stage_code SET NOT NULL,
    ALTER COLUMN phase_code SET NOT NULL,
    DROP COLUMN team_id;

ALTER TABLE public.sales_pipeline_stage
    RENAME CONSTRAINT pipeline_stages_pkey TO sales_pipeline_stage_pkey;
ALTER TABLE public.sales_pipeline_stage
    RENAME CONSTRAINT pipeline_stages_name_check TO sales_pipeline_stage_name_check;
ALTER TABLE public.sales_pipeline_stage DROP CONSTRAINT pipeline_stages_tone_check;
ALTER TABLE public.sales_pipeline_stage
    RENAME CONSTRAINT pipeline_stages_outcome_code_check
    TO sales_pipeline_stage_outcome_code_check;
ALTER TABLE public.sales_pipeline_stage
    RENAME CONSTRAINT pipeline_stages_position_check TO sales_pipeline_stage_position_check;

ALTER TABLE public.sales_pipeline_stage
    ADD CONSTRAINT sales_pipeline_stage_sales_pipeline_id_fkey
        FOREIGN KEY (sales_pipeline_id) REFERENCES public.sales_pipeline (id),
    ADD CONSTRAINT sales_pipeline_stage_stage_code_check CHECK (btrim(stage_code) <> ''),
    ADD CONSTRAINT sales_pipeline_stage_tone_check
        CHECK (tone IN ('gray', 'blue', 'purple', 'orange', 'green', 'red')),
    ADD CONSTRAINT sales_pipeline_stage_phase_code_check
        CHECK (phase_code IN ('sales', 'quote', 'contract', 'order', 'closed')),
    ADD CONSTRAINT sales_pipeline_stage_sales_pipeline_id_stage_code_key
        UNIQUE (sales_pipeline_id, stage_code),
    ADD CONSTRAINT sales_pipeline_stage_sales_pipeline_id_position_key
        UNIQUE (sales_pipeline_id, position),
    ADD CONSTRAINT sales_pipeline_stage_sales_pipeline_id_id_key
        UNIQUE (sales_pipeline_id, id);

ALTER TABLE public.contract RENAME TO sales_deal;
ALTER TABLE public.sales_deal RENAME COLUMN contract_no TO deal_no;
ALTER TABLE public.sales_deal RENAME COLUMN contact_id TO customer_contact_id;
ALTER TABLE public.sales_deal RENAME COLUMN stage_id TO sales_pipeline_stage_id;
ALTER TABLE public.sales_deal RENAME COLUMN amount TO deal_amount;
ALTER TABLE public.sales_deal RENAME COLUMN contract_date TO opened_on;
ALTER TABLE public.sales_deal RENAME COLUMN ends_on TO contract_ends_on;
ALTER TABLE public.sales_deal RENAME COLUMN position TO stage_position;

ALTER TABLE public.sales_deal
    ADD COLUMN sales_pipeline_id uuid,
    ADD COLUMN sales_deal_type_id uuid,
    ADD COLUMN closed_on date,
    ADD COLUMN quote_no text,
    ADD COLUMN quote_issued_on date,
    ADD COLUMN quote_valid_until date,
    ADD COLUMN contract_no text,
    ADD COLUMN contract_signed_on date;

UPDATE public.sales_deal AS deal
SET sales_pipeline_id = stage.sales_pipeline_id
FROM public.sales_pipeline_stage AS stage
WHERE stage.id = deal.sales_pipeline_stage_id;

UPDATE public.sales_deal AS deal
SET sales_deal_type_id = deal_type.id
FROM public.sales_deal_type AS deal_type
WHERE deal_type.team_id = deal.team_id AND deal_type.code = deal.contract_type;

-- old contract_date는 모든 행에서 딜 시작일로 보존한다. 과거 confirmed 행만
-- 실제 체결일로도 해석할 수 있어 contract_signed_on에 조건부 복사한다.
UPDATE public.sales_deal AS deal
SET contract_signed_on = deal.opened_on
FROM public.sales_pipeline_stage AS stage
WHERE stage.id = deal.sales_pipeline_stage_id AND stage.outcome_code = 'confirmed';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.sales_deal
        WHERE sales_pipeline_id IS NULL OR sales_deal_type_id IS NULL
    ) THEN
        RAISE EXCEPTION 'sales deal migration blocked: pipeline or deal type backfill failed';
    END IF;
END
$$;

ALTER TABLE public.sales_deal DROP CONSTRAINT contracts_stage_id_fkey;
ALTER TABLE public.sales_deal DROP COLUMN contract_type;

ALTER TABLE public.purchase_order RENAME COLUMN contract_id TO sales_deal_id;
ALTER TABLE public.purchase_order ADD COLUMN purchase_order_status_id uuid;

UPDATE public.purchase_order AS purchase_order
SET purchase_order_status_id = status.id
FROM public.purchase_order_status AS status
WHERE status.team_id = purchase_order.team_id AND status.code = purchase_order.stage_code;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.purchase_order
        WHERE sales_deal_id IS NULL OR purchase_order_status_id IS NULL
    ) THEN
        RAISE EXCEPTION 'purchase order migration blocked: deal or status backfill failed';
    END IF;
END
$$;

WITH desired_stage AS (
    SELECT purchase_order.sales_deal_id,
           CASE
               WHEN bool_or(status.outcome_code = 'in_progress') THEN 'order_in_progress'
               WHEN bool_or(status.code = 'delivered') THEN 'order_delivered'
               ELSE 'closed_cancelled'
           END AS stage_code
    FROM public.purchase_order AS purchase_order
    JOIN public.purchase_order_status AS status
      ON status.id = purchase_order.purchase_order_status_id
    WHERE purchase_order.deleted_at IS NULL
    GROUP BY purchase_order.sales_deal_id
)
UPDATE public.sales_deal AS deal
SET sales_pipeline_stage_id = target_stage.id
FROM desired_stage
JOIN public.sales_pipeline_stage AS target_stage
  ON target_stage.stage_code = desired_stage.stage_code
WHERE deal.id = desired_stage.sales_deal_id
  AND target_stage.sales_pipeline_id = deal.sales_pipeline_id;

-- closed_on은 확정 매출일이 아니라 파이프라인이 닫힌 날짜다.
UPDATE public.sales_deal AS deal
SET closed_on = deal.opened_on
FROM public.sales_pipeline_stage AS stage
WHERE stage.id = deal.sales_pipeline_stage_id AND stage.phase_code = 'closed';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.sales_deal
        WHERE contract_ends_on IS NOT NULL
          AND (contract_signed_on IS NULL OR contract_ends_on < contract_signed_on)
    ) THEN
        RAISE EXCEPTION
            'sales deal migration blocked: contract_ends_on requires a non-later signed date';
    END IF;
END
$$;

DROP INDEX public.orders_team_owner_due_idx;
DROP INDEX public.orders_contract_idx;

ALTER TABLE public.purchase_order
    ALTER COLUMN sales_deal_id SET NOT NULL,
    ALTER COLUMN purchase_order_status_id SET NOT NULL,
    DROP COLUMN customer_company_id,
    DROP COLUMN owner_member_id,
    DROP COLUMN stage_code;

ALTER TABLE public.activity RENAME COLUMN contract_id TO sales_deal_id;
ALTER TABLE public.activity RENAME COLUMN order_id TO purchase_order_id;
ALTER TABLE public.purchase_order_item RENAME COLUMN order_id TO purchase_order_id;
ALTER TABLE public.support_response RENAME COLUMN request_id TO support_request_id;
ALTER TABLE public.document RENAME COLUMN contract_id TO sales_deal_id;
ALTER TABLE public.document RENAME COLUMN order_id TO purchase_order_id;
ALTER TABLE public.agent_run RENAME COLUMN model_name TO llm_model_name;

UPDATE public.agent_run
SET source_refs = (source_refs - 'contract_id')
    || jsonb_build_object('sales_deal_id', source_refs -> 'contract_id')
WHERE jsonb_typeof(source_refs) = 'object' AND source_refs ? 'contract_id';

ALTER TABLE public.sales_deal RENAME CONSTRAINT contracts_pkey TO sales_deal_pkey;
ALTER TABLE public.sales_deal
    RENAME CONSTRAINT contracts_team_id_fkey TO sales_deal_team_id_fkey;
ALTER TABLE public.sales_deal
    RENAME CONSTRAINT contracts_contract_no_check TO sales_deal_deal_no_check;
ALTER TABLE public.sales_deal
    RENAME CONSTRAINT contracts_customer_company_id_fkey
    TO sales_deal_customer_company_id_fkey;
ALTER TABLE public.sales_deal
    RENAME CONSTRAINT contracts_contact_id_fkey TO sales_deal_customer_contact_id_fkey;
ALTER TABLE public.sales_deal
    RENAME CONSTRAINT contracts_owner_member_id_fkey TO sales_deal_owner_member_id_fkey;
ALTER TABLE public.sales_deal
    RENAME CONSTRAINT contracts_product_id_fkey TO sales_deal_product_id_fkey;
ALTER TABLE public.sales_deal
    RENAME CONSTRAINT contracts_title_check TO sales_deal_title_check;
ALTER TABLE public.sales_deal
    RENAME CONSTRAINT contracts_description_check TO sales_deal_description_check;
ALTER TABLE public.sales_deal
    RENAME CONSTRAINT contracts_amount_check TO sales_deal_deal_amount_check;
ALTER TABLE public.sales_deal
    RENAME CONSTRAINT contracts_warranty_terms_check TO sales_deal_warranty_terms_check;
ALTER TABLE public.sales_deal
    RENAME CONSTRAINT contracts_memo_check TO sales_deal_memo_check;
ALTER TABLE public.sales_deal
    RENAME CONSTRAINT contracts_position_check TO sales_deal_stage_position_check;
DROP INDEX public.contracts_team_stage_position_idx;
CREATE INDEX sales_deal_team_pipeline_stage_position_idx
    ON public.sales_deal (
        team_id, sales_pipeline_id, sales_pipeline_stage_id, stage_position
    )
    WHERE deleted_at IS NULL;
ALTER INDEX public.contracts_team_owner_date_idx
    RENAME TO sales_deal_team_owner_opened_on_idx;
ALTER INDEX public.contracts_ends_on_idx RENAME TO sales_deal_contract_ends_on_idx;

ALTER TABLE public.sales_deal
    ALTER COLUMN sales_pipeline_id SET NOT NULL,
    ALTER COLUMN sales_deal_type_id SET NOT NULL,
    ADD CONSTRAINT sales_deal_sales_deal_type_id_fkey
        FOREIGN KEY (sales_deal_type_id) REFERENCES public.sales_deal_type (id),
    ADD CONSTRAINT sales_deal_sales_pipeline_stage_membership_fkey
        FOREIGN KEY (sales_pipeline_id, sales_pipeline_stage_id)
        REFERENCES public.sales_pipeline_stage (sales_pipeline_id, id),
    ADD CONSTRAINT sales_deal_team_id_deal_no_key UNIQUE (team_id, deal_no),
    ADD CONSTRAINT sales_deal_team_id_quote_no_key UNIQUE (team_id, quote_no),
    ADD CONSTRAINT sales_deal_team_id_contract_no_key UNIQUE (team_id, contract_no),
    ADD CONSTRAINT sales_deal_quote_no_check
        CHECK (quote_no IS NULL OR btrim(quote_no) <> ''),
    ADD CONSTRAINT sales_deal_contract_no_check
        CHECK (contract_no IS NULL OR btrim(contract_no) <> ''),
    ADD CONSTRAINT sales_deal_closed_on_order_check
        CHECK (closed_on IS NULL OR closed_on >= opened_on),
    ADD CONSTRAINT sales_deal_quote_issued_on_check
        CHECK (quote_issued_on IS NULL OR quote_issued_on >= opened_on),
    ADD CONSTRAINT sales_deal_quote_valid_until_check
        CHECK (quote_valid_until IS NULL
               OR (quote_issued_on IS NOT NULL AND quote_valid_until >= quote_issued_on)),
    ADD CONSTRAINT sales_deal_contract_signed_on_check
        CHECK (contract_signed_on IS NULL OR contract_signed_on >= opened_on),
    ADD CONSTRAINT sales_deal_contract_ends_on_order_check
        CHECK (contract_ends_on IS NULL
               OR (contract_signed_on IS NOT NULL AND contract_ends_on >= contract_signed_on));

ALTER TABLE public.purchase_order RENAME CONSTRAINT orders_pkey TO purchase_order_pkey;
ALTER TABLE public.purchase_order
    RENAME CONSTRAINT orders_team_id_fkey TO purchase_order_team_id_fkey;
ALTER TABLE public.purchase_order
    RENAME CONSTRAINT orders_order_no_check TO purchase_order_order_no_check;
ALTER TABLE public.purchase_order
    RENAME CONSTRAINT orders_contract_id_fkey TO purchase_order_sales_deal_id_fkey;
ALTER TABLE public.purchase_order
    RENAME CONSTRAINT orders_supplier_name_check TO purchase_order_supplier_name_check;
ALTER TABLE public.purchase_order
    RENAME CONSTRAINT orders_memo_check TO purchase_order_memo_check;
ALTER INDEX public.orders_expected_receipt_idx RENAME TO purchase_order_expected_receipt_idx;

ALTER TABLE public.purchase_order
    ADD CONSTRAINT purchase_order_purchase_order_status_id_fkey
        FOREIGN KEY (purchase_order_status_id) REFERENCES public.purchase_order_status (id),
    ADD CONSTRAINT purchase_order_team_id_order_no_key UNIQUE (team_id, order_no),
    ADD CONSTRAINT purchase_order_due_on_order_check CHECK (due_on >= ordered_on),
    ADD CONSTRAINT purchase_order_expected_receipt_on_order_check
        CHECK (expected_receipt_on >= ordered_on);

CREATE INDEX purchase_order_team_due_idx
    ON public.purchase_order (team_id, due_on) WHERE deleted_at IS NULL;
CREATE INDEX purchase_order_sales_deal_idx
    ON public.purchase_order (sales_deal_id) WHERE deleted_at IS NULL;

ALTER TABLE public.purchase_order_item
    RENAME CONSTRAINT order_items_pkey TO purchase_order_item_pkey;
ALTER TABLE public.purchase_order_item
    RENAME CONSTRAINT order_items_order_id_fkey TO purchase_order_item_purchase_order_id_fkey;
ALTER TABLE public.purchase_order_item
    RENAME CONSTRAINT order_items_product_id_fkey TO purchase_order_item_product_id_fkey;
ALTER TABLE public.purchase_order_item
    RENAME CONSTRAINT order_items_quantity_check TO purchase_order_item_quantity_check;
ALTER TABLE public.purchase_order_item
    RENAME CONSTRAINT order_items_unit_price_check TO purchase_order_item_unit_price_check;
ALTER TABLE public.purchase_order_item
    RENAME CONSTRAINT order_items_position_check TO purchase_order_item_position_check;
ALTER INDEX public.order_items_order_position_idx
    RENAME TO purchase_order_item_purchase_order_position_idx;

ALTER TABLE public.support_response
    RENAME CONSTRAINT support_responses_pkey TO support_response_pkey;
ALTER TABLE public.support_response
    RENAME CONSTRAINT support_responses_request_id_fkey
    TO support_response_support_request_id_fkey;
ALTER TABLE public.support_response
    RENAME CONSTRAINT support_responses_responder_member_id_fkey
    TO support_response_responder_member_id_fkey;
ALTER TABLE public.support_response
    RENAME CONSTRAINT support_responses_body_check TO support_response_body_check;
ALTER INDEX public.support_responses_request_responded_idx
    RENAME TO support_response_support_request_responded_idx;

ALTER TABLE public.activity RENAME CONSTRAINT activities_pkey TO activity_pkey;
ALTER TABLE public.activity
    RENAME CONSTRAINT activities_team_id_fkey TO activity_team_id_fkey;
ALTER TABLE public.activity
    RENAME CONSTRAINT activities_owner_member_id_fkey TO activity_owner_member_id_fkey;
ALTER TABLE public.activity
    RENAME CONSTRAINT activities_customer_contact_id_fkey
    TO activity_customer_contact_id_fkey;
ALTER TABLE public.activity
    RENAME CONSTRAINT activities_end_user_contact_id_fkey
    TO activity_end_user_contact_id_fkey;
ALTER TABLE public.activity
    RENAME CONSTRAINT activities_activity_type_check TO activity_activity_type_check;
ALTER TABLE public.activity
    RENAME CONSTRAINT activities_title_check TO activity_title_check;
ALTER TABLE public.activity
    RENAME CONSTRAINT activities_location_check TO activity_location_check;
ALTER TABLE public.activity RENAME CONSTRAINT activities_note_check TO activity_note_check;
ALTER TABLE public.activity
    RENAME CONSTRAINT activities_ends_after_start TO activity_ends_after_start;
ALTER TABLE public.activity
    RENAME CONSTRAINT activities_product_id_fkey TO activity_product_id_fkey;
ALTER TABLE public.activity
    RENAME CONSTRAINT activities_contract_id_fkey TO activity_sales_deal_id_fkey;
ALTER TABLE public.activity
    RENAME CONSTRAINT activities_order_id_fkey TO activity_purchase_order_id_fkey;
ALTER INDEX public.activities_team_starts_idx RENAME TO activity_team_starts_idx;
ALTER INDEX public.activities_team_owner_starts_idx RENAME TO activity_team_owner_starts_idx;
ALTER INDEX public.activities_customer_contact_idx RENAME TO activity_customer_contact_idx;
ALTER INDEX public.activities_product_idx RENAME TO activity_product_idx;
ALTER INDEX public.activities_contract_idx RENAME TO activity_sales_deal_idx;
ALTER INDEX public.activities_order_idx RENAME TO activity_purchase_order_idx;

ALTER TABLE public.document RENAME CONSTRAINT documents_pkey TO document_pkey;
ALTER TABLE public.document
    RENAME CONSTRAINT documents_team_id_fkey TO document_team_id_fkey;
ALTER TABLE public.document
    RENAME CONSTRAINT documents_created_by_member_id_fkey
    TO document_created_by_member_id_fkey;
ALTER TABLE public.document
    RENAME CONSTRAINT documents_document_no_check TO document_document_no_check;
ALTER TABLE public.document
    RENAME CONSTRAINT documents_category_code_check TO document_category_code_check;
ALTER TABLE public.document RENAME CONSTRAINT documents_title_check TO document_title_check;
ALTER TABLE public.document
    RENAME CONSTRAINT documents_description_check TO document_description_check;
ALTER TABLE public.document
    RENAME CONSTRAINT documents_customer_company_id_fkey
    TO document_customer_company_id_fkey;
ALTER TABLE public.document
    RENAME CONSTRAINT documents_contract_id_fkey TO document_sales_deal_id_fkey;
ALTER TABLE public.document
    RENAME CONSTRAINT documents_order_id_fkey TO document_purchase_order_id_fkey;
ALTER TABLE public.document RENAME CONSTRAINT documents_tags_check TO document_tags_check;
ALTER INDEX public.documents_team_created_idx RENAME TO document_team_created_idx;
ALTER INDEX public.documents_customer_company_idx RENAME TO document_customer_company_idx;

ALTER TABLE public.agent_run RENAME CONSTRAINT agent_runs_pkey TO agent_run_pkey;
ALTER TABLE public.agent_run
    RENAME CONSTRAINT agent_runs_team_id_fkey TO agent_run_team_id_fkey;
ALTER TABLE public.agent_run
    RENAME CONSTRAINT agent_runs_parent_run_id_fkey TO agent_run_parent_run_id_fkey;
ALTER TABLE public.agent_run
    RENAME CONSTRAINT agent_runs_requested_by_member_id_fkey
    TO agent_run_requested_by_member_id_fkey;
ALTER TABLE public.agent_run
    RENAME CONSTRAINT agent_runs_agent_code_check TO agent_run_agent_code_check;
ALTER TABLE public.agent_run
    RENAME CONSTRAINT agent_runs_trigger_code_check TO agent_run_trigger_code_check;
ALTER TABLE public.agent_run
    RENAME CONSTRAINT agent_runs_status_code_check TO agent_run_status_code_check;
ALTER TABLE public.agent_run
    RENAME CONSTRAINT agent_runs_model_name_check TO agent_run_llm_model_name_check;
ALTER TABLE public.agent_run
    RENAME CONSTRAINT agent_runs_prompt_version_check TO agent_run_prompt_version_check;
ALTER TABLE public.agent_run
    RENAME CONSTRAINT agent_runs_error_message_check TO agent_run_error_message_check;
ALTER TABLE public.agent_run
    RENAME CONSTRAINT agent_runs_not_own_parent TO agent_run_not_own_parent;
ALTER TABLE public.agent_run
    RENAME CONSTRAINT agent_runs_idempotency_requester TO agent_run_idempotency_requester;
ALTER TABLE public.agent_run
    RENAME CONSTRAINT agent_runs_requested_by_member_id_idempotency_key_key
    TO agent_run_requested_by_member_id_idempotency_key_key;
ALTER INDEX public.agent_runs_team_status_idx RENAME TO agent_run_team_status_idx;
ALTER INDEX public.agent_runs_parent_idx RENAME TO agent_run_parent_idx;

COMMIT;
