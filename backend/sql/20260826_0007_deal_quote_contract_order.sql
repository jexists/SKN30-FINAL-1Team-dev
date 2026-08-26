-- 견적과 계약이 딜과 구분되어 자기 데이터를 갖게 한다.
--
-- 지금까지 견적현황·계약현황은 sales_deal 을 phase_code 로만 걸러 보여 주는 뷰였다.
-- 그래서 세 화면의 "금액" 이 전부 deal_amount 하나를 읽었고, 견적가를 적으면 영업
-- 예상금액이 덮이고 계약가를 적으면 견적가가 사라졌다. 단계별 값이 남지 않으니
-- 계약 화면에서 "이 건의 견적이 얼마였나" 를 물어볼 데가 없다.
--
-- 딜:견적:계약 = 1:1 이라 견적·계약을 별도 테이블로 떼지 않고 sales_deal 의 컬럼으로
-- 둔다. 기존 quote_*/contract_* 컬럼은 그대로 두고 금액과 상태만 더한다. 컬럼으로
-- 표현할 수 없는 것(다건이거나 팀이 정하는 룩업)만 새 테이블로 만든다.
--
-- deal_amount 는 건드리지 않는다. dashboard 의 월매출·확정금액 합계와 칸반 카드가
-- 이미 읽고 있어서 뜻을 바꾸면 대시보드 숫자가 조용히 달라진다. 영업 단계의
-- 예상금액으로 그대로 둔다.
--
-- 견적/계약 상태는 파이프라인 단계(sales_pipeline_stage)와 다른 축이다. 파이프라인은
-- "딜이 지금 어느 국면인가" 이고, 여기 상태는 "그 국면 안에서 서류가 어디까지 갔나"
-- 이다. purchase_order_status 가 발주에 대해 하는 일과 같아 모양도 그대로 베낀다.
--
-- 삭제·초기화는 없다. 새 컬럼은 전부 NULL 허용이거나 딜에서 백필할 수 있다.

BEGIN;

-- 1) 견적 상태. purchase_order_status 와 같은 모양이다.
CREATE TABLE public.quote_status (
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

CREATE INDEX quote_status_team_position_idx
    ON public.quote_status (team_id, "position")
    WHERE deleted_at IS NULL;

COMMENT ON TABLE public.quote_status IS
    '견적서 한 장의 진행 상태. 팀이 늘리고 줄인다. 파이프라인 단계와는 다른 축이다.';

CREATE TABLE public.contract_status (
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

CREATE INDEX contract_status_team_position_idx
    ON public.contract_status (team_id, "position")
    WHERE deleted_at IS NULL;

COMMENT ON TABLE public.contract_status IS
    '계약서 한 장의 진행 상태. quote_status 와 같은 모양이고 값만 다르다.';

-- 2) 견적 품목. 딜:견적이 1:1 이라 별도 견적 부모 없이 딜에 직접 매단다.
--    purchase_order_item 과 같은 모양이다.
CREATE TABLE public.sales_deal_item (
    id uuid PRIMARY KEY,
    sales_deal_id uuid NOT NULL
        REFERENCES public.sales_deal (id) ON DELETE CASCADE,
    product_id uuid NOT NULL REFERENCES public.product (id),
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price bigint NOT NULL CHECK (unit_price >= 0),
    "position" integer NOT NULL CHECK ("position" >= 0)
);

CREATE INDEX sales_deal_item_sales_deal_position_idx
    ON public.sales_deal_item (sales_deal_id, "position");

COMMENT ON TABLE public.sales_deal_item IS
    '견적 품목. sales_deal.quote_amount 는 이 줄들의 수량×단가 합이다.';

-- 3) 미팅 대상자. customer_contact_assignee 와 같은 모양이다.
--    sales_deal.customer_contact_id 는 대표 담당자로 남는다. 조회 스코프가 그 컬럼을
--    보기 때문에 단일 컬럼이 계속 필요하다.
CREATE TABLE public.sales_deal_participant (
    sales_deal_id uuid NOT NULL
        REFERENCES public.sales_deal (id) ON DELETE CASCADE,
    customer_contact_id uuid NOT NULL REFERENCES public.customer_contact (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (sales_deal_id, customer_contact_id)
);

CREATE INDEX sales_deal_participant_contact_idx
    ON public.sales_deal_participant (customer_contact_id);

COMMENT ON TABLE public.sales_deal_participant IS
    '미팅 대상자. 대표 담당자(sales_deal.customer_contact_id)와는 별개의 목록이다.';

-- 4) 딜에 견적·계약의 자기 값을 더한다.
--    상태 컬럼이 NULL 이면 아직 그 국면에 들어가지 않았다는 뜻이고, 견적현황·계약현황
--    목록이 그것으로 갈린다. phase_code 로 거르면 계약으로 넘어간 딜이 견적번호를
--    그대로 들고 있는데도 견적현황에서 사라진다.
ALTER TABLE public.sales_deal
    ADD COLUMN quote_status_id uuid REFERENCES public.quote_status (id),
    ADD COLUMN contract_status_id uuid REFERENCES public.contract_status (id),
    ADD COLUMN quote_amount bigint CHECK (quote_amount IS NULL OR quote_amount >= 0),
    ADD COLUMN contract_amount bigint CHECK (contract_amount IS NULL OR contract_amount >= 0),
    ADD COLUMN quote_delivery_terms text
        CHECK (quote_delivery_terms IS NULL OR btrim(quote_delivery_terms) <> '');

COMMENT ON COLUMN public.sales_deal.quote_status_id IS
    '견적 상태. NULL 이면 아직 견적이 없다는 뜻이고 견적현황 목록이 이 조건으로 갈린다.';
COMMENT ON COLUMN public.sales_deal.contract_status_id IS
    '계약 상태. NULL 이면 아직 계약이 없다.';
COMMENT ON COLUMN public.sales_deal.quote_amount IS
    '견적금액. 품목이 있으면 서버가 sales_deal_item 의 합으로 채운다.';
COMMENT ON COLUMN public.sales_deal.contract_amount IS
    '계약금액. 견적가에서 협의로 조정된 값이 남는다. deal_amount(영업 예상금액)와 다르다.';
COMMENT ON COLUMN public.sales_deal.quote_delivery_terms IS
    '납품예상일자 문구. "계약완료 후 14일 이내" 처럼 날짜로 표현할 수 없어 text 다.';

-- 5) 발주서 양식이 요구하는 항목. 부서 둘은 고정 문구라 DEFAULT 를 남겨 둔다.
ALTER TABLE public.purchase_order
    ADD COLUMN request_department text NOT NULL DEFAULT '영업팀'
        CHECK (btrim(request_department) <> ''),
    ADD COLUMN cooperation_department text NOT NULL DEFAULT '생산팀'
        CHECK (btrim(cooperation_department) <> ''),
    ADD COLUMN created_by_member_id uuid REFERENCES public.member (id),
    ADD COLUMN expected_customer_company_id uuid REFERENCES public.customer_company (id);

-- 기존 발주는 걸린 딜에서 가져온다. 작성자는 딜 담당자, 납품예상 거래처는 딜 고객사다.
UPDATE public.purchase_order AS po
SET created_by_member_id = sd.owner_member_id,
    expected_customer_company_id = sd.customer_company_id
FROM public.sales_deal AS sd
WHERE sd.id = po.sales_deal_id;

ALTER TABLE public.purchase_order
    ALTER COLUMN created_by_member_id SET NOT NULL,
    ALTER COLUMN expected_customer_company_id SET NOT NULL;

COMMENT ON COLUMN public.purchase_order.created_by_member_id IS
    '발주서를 쓴 사람. 로그인 사용자로 서버가 채우며 등록 후 바뀌지 않는다.';
COMMENT ON COLUMN public.purchase_order.expected_customer_company_id IS
    '납품예상 거래처. 보통 딜의 고객사지만 다른 곳으로 보내는 경우가 있어 따로 둔다.';

CREATE INDEX purchase_order_expected_company_idx
    ON public.purchase_order (expected_customer_company_id)
    WHERE deleted_at IS NULL;

-- 6) 발주 상태 라벨 하나. 화면이 "발주취소" 로 읽어야 다른 취소와 섞이지 않는다.
--    seed_demo_auth 는 ON CONFLICT DO NOTHING 이라 기존 행을 고치지 않는다.
UPDATE public.purchase_order_status
SET name = '발주취소', updated_at = now()
WHERE code = 'cancelled' AND name = '취소';

ALTER TABLE public.quote_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contract_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales_deal_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales_deal_participant ENABLE ROW LEVEL SECURITY;

COMMIT;
