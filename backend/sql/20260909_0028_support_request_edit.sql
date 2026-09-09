-- 고객불만 본문을 고칠 수 있게 한다.
--
-- 지금까지 고객불만은 등록과 상태 전환만 되고 한 번 적은 제목·내용은 고칠 수 없었다.
-- 오타 하나를 바로잡으려 같은 건을 다시 등록하는 일이 생긴다.
--
-- 화면에는 "수정일시" 한 줄만 보인다. 바뀌기 전 값은 되돌릴 일에 대비한 백업으로만 두고
-- 읽는 API 도 화면도 두지 않는다. 꺼낼 일이 생기면 DB 에서 직접 본다.
--
-- 더하기만 하므로 아직 물러나지 않은 구코드도 깨지지 않는다. 적용 순서는 자유다.

BEGIN;

ALTER TABLE public.support_request ADD COLUMN updated_at timestamptz;

COMMENT ON COLUMN public.support_request.updated_at IS
    '마지막으로 본문을 고친 시각. 한 번도 고치지 않았으면 NULL. registered_at 은 등록 시각이라 다르다.';

CREATE TABLE public.support_request_edit_backup (
    id                 uuid PRIMARY KEY,
    support_request_id uuid NOT NULL REFERENCES public.support_request(id),
    editor_member_id   uuid NOT NULL REFERENCES public.member(id),
    edited_at          timestamptz NOT NULL DEFAULT now(),
    -- 고치기 직전의 값 그대로. 바뀐 칸만 담지 않는다. 되돌릴 때 한 행이면 충분해야 한다.
    title              text NOT NULL,
    body               text NOT NULL,
    is_urgent          boolean NOT NULL,
    occurred_at        timestamptz NOT NULL
);

COMMENT ON TABLE public.support_request_edit_backup IS
    '고객불만을 고치기 직전 값의 백업. 쓰기 전용이며 읽는 API 가 없다. 되돌릴 일에만 쓴다.';

CREATE INDEX support_request_edit_backup_request_idx
    ON public.support_request_edit_backup (support_request_id, edited_at);

COMMIT;
