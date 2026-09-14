-- CS대응(고객불만)을 지울 수 있게 한다. 지우는 건 등록한 본인과 팀장이다.
--
-- 행을 실제로 지우면 안 된다. support_response 와 support_request_edit_backup 이
-- ON DELETE 옵션 없이 support_request 를 참조하므로 DELETE 는 외래키 오류로 막히고,
-- 참조를 먼저 지우면 대응 이력과 수정 전 백업(0028 이 만든 표)이 함께 사라진다.
--
-- customer_contact, document, sales_deal, purchase_order, notice 가 이미 쓰는
-- deleted_at 방식을 따른다. 목록·상세·탭 건수·대시보드 C/S 카드와 계약 일정 신호는
-- deleted_at IS NULL 만 본다.

BEGIN;

ALTER TABLE public.support_request
    ADD COLUMN deleted_at timestamptz;

COMMENT ON COLUMN public.support_request.deleted_at IS
    '삭제 시각. NULL 이면 살아 있는 건이다. 등록한 본인과 팀장이 채울 수 있다.';

-- 목록과 상세가 늘 살아 있는 건만 찾는다. 지운 건이 쌓여도 그쪽은 훑지 않는다.
CREATE INDEX support_request_active_idx
    ON public.support_request (id)
    WHERE deleted_at IS NULL;

COMMIT;
