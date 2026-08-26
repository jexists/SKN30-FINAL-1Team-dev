-- 고객 한 사람의 방문 여부를 남긴다.
--
-- 지금까지 "이 고객을 만나 봤는가"는 activity 를 뒤져야 알 수 있었다. 목록에서 한눈에
-- 가르고 싶다는 요구가 있어 고객 행 자체에 표시를 둔다. 활동 기록에서 파생하지 않고
-- 담당자가 직접 켜고 끄는 값이다. 둘을 잇는 자동 갱신은 지금 넣지 않는다.
--
-- 새로 등록하는 고객은 아직 만나기 전이므로 미방문(false)에서 시작한다. 기존 행도 같다.

BEGIN;

ALTER TABLE public.customer_contact
    ADD COLUMN visited boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN public.customer_contact.visited IS
    '방문 여부. false 가 미방문이고 새 고객의 기본값이다. 담당자가 직접 바꾼다.';

COMMIT;
