-- 고객의 담당자를 여러 명 둘 수 있게 하고, 등록한 사람을 따로 남긴다.
--
-- 지금까지 customer_contact.owner_member_id 하나가 "등록한 사람"과 "담당하는 사람"을 겸했다.
-- 팀장이 남을 담당자로 지정할 수 있게 되면서 둘이 갈라진다. owner_member_id 는 대표 담당자로
-- 남는다. 고객 조회 스코프가 여러 라우터에서 이 컬럼에 걸려 있어 단일 컬럼이 계속 필요하다.
--
-- 회사에는 사업자등록번호를 함께 둔다. 같은 이름의 고객사를 구분하는 데 쓴다.

BEGIN;

-- team.business_no (20260823_0002) 와 같은 규칙으로 저장한다.
ALTER TABLE public.customer_company
    ADD COLUMN business_no text
        CHECK (business_no IS NULL OR business_no ~ '^[0-9]{10}$');

COMMENT ON COLUMN public.customer_company.business_no IS
    '사업자등록번호 10자리. 하이픈 없이 저장한다.';

ALTER TABLE public.customer_contact
    ADD COLUMN created_by_member_id uuid REFERENCES public.member (id);

-- 기존 행은 등록자와 담당자가 같았다.
UPDATE public.customer_contact SET created_by_member_id = owner_member_id;

ALTER TABLE public.customer_contact
    ALTER COLUMN created_by_member_id SET NOT NULL;

COMMENT ON COLUMN public.customer_contact.created_by_member_id IS
    '고객을 등록한 사람. 등록 후 바뀌지 않는다.';
COMMENT ON COLUMN public.customer_contact.owner_member_id IS
    '대표 담당자. customer_contact_assignee 의 첫 번째와 같다. 조회 스코프가 이 컬럼을 본다.';

CREATE TABLE public.customer_contact_assignee (
    customer_contact_id uuid NOT NULL
        REFERENCES public.customer_contact (id) ON DELETE CASCADE,
    member_id uuid NOT NULL REFERENCES public.member (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (customer_contact_id, member_id)
);

COMMENT ON TABLE public.customer_contact_assignee IS
    '고객 한 건의 담당자. 대표 담당자도 여기에 함께 들어간다.';

-- 담당자로 지정된 고객을 훑는 조회가 member_id 로 들어온다.
CREATE INDEX customer_contact_assignee_member_idx
    ON public.customer_contact_assignee (member_id);

-- 기존 담당자 1명을 그대로 옮긴다.
INSERT INTO public.customer_contact_assignee (customer_contact_id, member_id)
SELECT id, owner_member_id FROM public.customer_contact;

ALTER TABLE public.customer_contact_assignee ENABLE ROW LEVEL SECURITY;

COMMIT;
