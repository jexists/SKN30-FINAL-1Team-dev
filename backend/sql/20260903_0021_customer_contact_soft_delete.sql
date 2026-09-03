-- 고객을 지울 수 있게 한다. 지우는 건 팀장뿐이다.
--
-- 행을 실제로 지우면 안 된다. activity, sales_deal, sales_deal_participant 가 ON DELETE
-- 옵션 없이 customer_contact 를 참조하므로 DELETE 는 외래키 오류로 막히고, 참조를 먼저
-- 끊으면 딜과 일정에서 누구를 만난 기록인지가 조용히 사라진다.
--
-- sales_deal, purchase_order, report, notice 가 이미 쓰는 deleted_at 방식을 따른다.
-- 고르는 자리(목록, 일정·딜의 고객 선택)는 deleted_at IS NULL 만 보고, 이미 연결된 것을
-- 보여 주는 자리는 걸러내지 않아 지난 기록이 그대로 남는다.

BEGIN;

ALTER TABLE public.customer_contact
    ADD COLUMN deleted_at timestamptz;

COMMENT ON COLUMN public.customer_contact.deleted_at IS
    '삭제 시각. NULL 이면 살아 있는 고객이다. 팀장만 채울 수 있다.';

-- 목록과 상세가 늘 살아 있는 고객만 찾는다. 지운 고객이 쌓여도 그쪽은 훑지 않는다.
CREATE INDEX customer_contact_active_idx
    ON public.customer_contact (id)
    WHERE deleted_at IS NULL;

COMMIT;
