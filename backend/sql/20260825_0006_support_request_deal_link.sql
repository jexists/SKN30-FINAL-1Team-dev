-- 고객불만을 담당자 대신 회사와 계약건에 맨다.
--
-- 지금까지 support_request 는 customer_contact_id 하나로만 고객 쪽에 붙어 있었다.
-- 그래서 "어느 계약의 어느 제품에 대한 불만인가" 를 물어볼 데가 없었고, 워런티가
-- 걸린 건인지도 알 수 없었다. 불만은 담당자 개인이 아니라 회사가 산 물건에 대해
-- 생기므로 회사(customer_company)와 계약건(sales_deal)에 맨다. 담당자 연결은 뗀다.
--
-- 제품과 워런티는 컬럼을 따로 두지 않는다. sales_deal 이 product_id 와 warranty_terms
-- 를 이미 들고 있어 딜 하나만 매면 둘 다 따라온다.
--
-- 회사는 딜을 거쳐 유도할 수도 있지만 컬럼으로 저장한다. 불만이 어느 회사 건인지는
-- 조인으로 계산하는 값이 아니라 저장된 사실이어야 한다. 대신 두 값이 어긋나면 안 되므로
-- 복합 외래키로 DB 가 일치를 보장한다. sales_deal 이 sales_pipeline_stage 를 참조하는
-- 방식과 같다.
--
-- 상태는 두 가지(처리중·처리완료)에서 네 가지(접수·원인파악·처리중·처리완료)로 늘린다.
-- 지금까지 값 검사는 Pydantic 에만 있었는데, 값이 늘었으니 DB 에도 CHECK 를 건다.
--
-- occurred_at(발생 시각)은 registered_at(등록 시각)과 다른 값이다. registered_at 은
-- 시스템이 찍는 감사값이고 occurred_at 은 접수자가 "언제 일어난 일인지" 를 직접 넣는다.

BEGIN;

-- 1) 기존 행 제거. sales_deal_id 를 NOT NULL 로 세워야 하는데 기존 불만에는 어느 딜에
--    속하는지 알 근거가 없다. 담당자의 회사에 딜이 여럿이면 고를 방법이 없고 하나도
--    없을 수도 있다. 개발 DB 의 데모 데이터라 지우고 새 스키마로 시작한다.
DELETE FROM public.support_response;
DELETE FROM public.support_request;

-- 2) 딜을 (id, customer_company_id) 로도 참조할 수 있게 유일성을 세운다. id 가 이미 PK
--    라 이 인덱스가 행을 더 좁히지는 않는다. 3) 의 복합 외래키가 참조할 대상을 만드는
--    것이 목적이다.
ALTER TABLE public.sales_deal
    ADD CONSTRAINT sales_deal_id_customer_company_key UNIQUE (id, customer_company_id);

-- 3) 회사와 계약건. 단일 외래키(customer_company.id, sales_deal.id)는 두지 않는다.
--    바로 아래 복합 외래키가 둘을 이미 포함하며, sales_deal 이 sales_pipeline_id 에
--    중복 외래키를 두지 않는 것과 같은 이유다.
ALTER TABLE public.support_request
    ADD COLUMN customer_company_id uuid NOT NULL,
    ADD COLUMN sales_deal_id uuid NOT NULL;

COMMENT ON COLUMN public.support_request.customer_company_id IS
    '불만을 낸 고객사. sales_deal 의 고객사와 같아야 하며 복합 외래키가 보장한다.';
COMMENT ON COLUMN public.support_request.sales_deal_id IS
    '불만이 걸린 계약건. 관련 제품과 워런티는 이 딜의 product_id·warranty_terms 다.';

-- 두 컬럼을 하나의 복합 외래키로 묶어 불만의 회사가 그 딜의 회사와 다를 수 없게 한다.
-- ON UPDATE CASCADE: 딜의 고객사를 옮기면 그 딜에 달린 불만도 따라간다. 안 걸면 불만이
-- 붙은 딜은 고객사를 고칠 수 없게 막혀 버린다.
ALTER TABLE public.support_request
    ADD CONSTRAINT support_request_sales_deal_company_membership_fkey
    FOREIGN KEY (sales_deal_id, customer_company_id)
    REFERENCES public.sales_deal (id, customer_company_id) ON UPDATE CASCADE;

-- 4) 담당자 연결 제거. 불만은 회사·계약 단위이지 담당자 단위가 아니다.
ALTER TABLE public.support_request
    DROP COLUMN customer_contact_id;

-- 5) 발생 시각. DEFAULT 는 두지 않는다. 앱이 항상 값을 넣고, tests/test_models.py 가
--    대조하는 server_default 문자열을 Postgres 가 정규화해 되돌려 주면서 어긋날 여지를
--    남기지 않는다. 기본값(지금 시각)은 등록 화면이 채워 준다.
ALTER TABLE public.support_request
    ADD COLUMN occurred_at timestamptz NOT NULL;

COMMENT ON COLUMN public.support_request.occurred_at IS
    '불만이 일어난 시각. 접수자가 직접 넣는다. registered_at(등록 시각)과 다르다.';

-- 6) 상태 네 가지. baseline 이 건 검사는 "비어 있지 않음" 뿐이고 Postgres 가
--    support_request_status_code_check 라는 이름을 자동으로 붙여 두었다. 값 목록이 그
--    조건을 이미 포함하므로 이름을 나누지 않고 같은 자리에서 갈아 끼운다.
ALTER TABLE public.support_request
    DROP CONSTRAINT support_request_status_code_check;

ALTER TABLE public.support_request
    ADD CONSTRAINT support_request_status_code_check
    CHECK (status_code IN ('received', 'diagnosing', 'in_progress', 'completed'));

COMMENT ON COLUMN public.support_request.status_code IS
    'received 접수 / diagnosing 원인파악 / in_progress 처리중 / completed 처리완료.';

-- 7) 인덱스. Postgres 는 외래키를 거는 쪽에 인덱스를 만들어 주지 않는다. 목록이 딜로
--    조인하고 3) 의 ON UPDATE CASCADE 도 이 인덱스를 탄다.
CREATE INDEX support_request_sales_deal_company_idx
    ON public.support_request (sales_deal_id, customer_company_id);

CREATE INDEX support_request_team_company_idx
    ON public.support_request (team_id, customer_company_id);

COMMIT;
