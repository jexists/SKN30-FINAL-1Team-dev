-- 공지와 팀장 지시사항을 팀장이 직접 관리하게 한다.
--
-- 지금까지 notice 는 recipient_member_id 하나로 "없으면 팀 공지, 있으면 개인 지시" 를 겸했다.
-- 지시 한 건을 여러 명에게 보내야 하므로 종류(type)를 컬럼으로 세우고 수신자는 notice_target
-- 으로 옮긴다. 옮긴 뒤 recipient_member_id 는 뗀다.
--
-- 노출 기간은 date 다. 업무상 의미가 "게시 기간" 이지 "게시 시각" 이 아니고, 기준 시간대가
-- Asia/Seoul 이라 timestamptz 로 두면 UTC 로 비교되는 하루가 화면이 말하는 하루와 어긋난다.
-- 시작일과 종료일 모두 그 날을 포함한다. 종료일이 없으면 무기한이다.
--
-- 본문(body)은 이제 편집기가 만든 HTML 이다. 저장 직전에 서버(app/services/html_sanitize.py)가
-- 허용한 태그만 남긴다. 본문 안의 사진은 notice_image 가 가리키는 저장소 객체다.

BEGIN;

-- 1) 종류. 기존 행은 수신자 유무로 가른다.
ALTER TABLE public.notice
    ADD COLUMN type text CHECK (type IN ('NOTICE', 'DIRECTIVE'));

UPDATE public.notice
   SET type = CASE WHEN recipient_member_id IS NULL THEN 'NOTICE' ELSE 'DIRECTIVE' END;

ALTER TABLE public.notice
    ALTER COLUMN type SET NOT NULL;

COMMENT ON COLUMN public.notice.type IS
    'NOTICE 는 팀 전체 공지, DIRECTIVE 는 notice_target 이 가리키는 사람에게 가는 지시다.';

-- 2) 노출 기간. 시작일은 기존 게시 시각의 서울 날짜로 백필하고 종료일은 비운다(무기한).
--    DEFAULT 는 두지 않는다. 앱이 항상 값을 넣고, tests/test_models.py 가 대조하는
--    server_default 문자열을 Postgres 가 정규화해 되돌려 주면서 어긋날 여지를 남기지 않는다.
ALTER TABLE public.notice
    ADD COLUMN display_start_date date,
    ADD COLUMN display_end_date date;

UPDATE public.notice
   SET display_start_date = (published_at AT TIME ZONE 'Asia/Seoul')::date;

ALTER TABLE public.notice
    ALTER COLUMN display_start_date SET NOT NULL;

ALTER TABLE public.notice
    ADD CONSTRAINT notice_display_range_check
        CHECK (display_end_date IS NULL OR display_end_date >= display_start_date);

COMMENT ON COLUMN public.notice.display_start_date IS
    '노출 시작일(Asia/Seoul, 그 날 포함). 이 날부터 화면에 선다.';
COMMENT ON COLUMN public.notice.display_end_date IS
    '노출 종료일(Asia/Seoul, 그 날 포함). NULL 이면 무기한이다.';

-- 3) 숨김과 정렬. 숨김은 지우는 것이 아니라 잠깐 내리는 것이다.
ALTER TABLE public.notice
    ADD COLUMN is_hidden boolean NOT NULL DEFAULT false,
    ADD COLUMN sort_order integer NOT NULL DEFAULT 0;

COMMENT ON COLUMN public.notice.is_hidden IS
    '켜면 팀장 관리 화면에만 남고 대시보드와 목록에서 빠진다.';
COMMENT ON COLUMN public.notice.sort_order IS
    '작을수록 위에 선다. 같으면 published_at 최신순이다.';

-- 4) 수정과 삭제 흔적. activity, sales_deal 의 deleted_at 과 같은 뜻이다.
ALTER TABLE public.notice
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN deleted_at timestamptz;

COMMENT ON COLUMN public.notice.deleted_at IS
    '삭제한 시각. 행을 지우지 않고 이 값으로 가린다.';
COMMENT ON COLUMN public.notice.body IS
    '허용 태그만 남긴 HTML. app/services/html_sanitize.py 를 지나야 들어온다.';

-- 5) 수신자 매핑. activity_companion 과 같은 모양이다.
CREATE TABLE public.notice_target (
    notice_id uuid NOT NULL
        REFERENCES public.notice (id) ON DELETE CASCADE,
    member_id uuid NOT NULL REFERENCES public.member (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (notice_id, member_id)
);

COMMENT ON TABLE public.notice_target IS
    '지시 한 건의 수신자. 공지(NOTICE)에는 행이 없다. created_at 순서가 표시 순서다.';

-- 자기에게 온 지시를 훑는 조회가 member_id 로 들어온다.
CREATE INDEX notice_target_member_idx ON public.notice_target (member_id);

-- 기존 수신자 1명을 그대로 옮긴다.
INSERT INTO public.notice_target (notice_id, member_id)
SELECT id, recipient_member_id
  FROM public.notice
 WHERE recipient_member_id IS NOT NULL;

-- 6) 본문에 넣은 사진. 편집기가 올리면 여기에 한 행이 남고 본문에는 id 만 박힌다.
--    storage_key 는 product.image_storage_key 와 같은 뜻이며 API 응답에 나가지 않는다.
CREATE TABLE public.notice_image (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.team (id),
    uploaded_by_member_id uuid NOT NULL REFERENCES public.member (id),
    storage_key text NOT NULL CHECK (btrim(storage_key) <> ''),
    media_type text NOT NULL CHECK (btrim(media_type) <> ''),
    created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.notice_image IS
    '공지 본문에 들어간 사진. 본문 HTML 은 /notice-images/{id} 로만 가리키고, 실제 주소는 '
    '읽을 때마다 서명 URL 로 새로 발급한다.';

CREATE INDEX notice_image_team_idx ON public.notice_image (team_id);

-- 7) 옛 인덱스와 컬럼을 뗀다. 조회 조건이 recipient_member_id 를 더 보지 않는다.
DROP INDEX IF EXISTS public.notice_team_recipient_published_idx;

ALTER TABLE public.notice
    DROP COLUMN recipient_member_id;

-- 팀원 목록과 팀장 관리 목록이 모두 (team_id, type) 으로 좁히고 sort_order, published_at 으로
-- 세운다. 지워진 행은 어느 쪽도 보지 않는다.
CREATE INDEX notice_team_type_order_idx
    ON public.notice (team_id, type, sort_order, published_at DESC)
    WHERE deleted_at IS NULL;

-- 지금 화면에 서는 것만 훑는 대시보드 경로.
CREATE INDEX notice_visible_idx
    ON public.notice (team_id, type, display_start_date, display_end_date)
    WHERE deleted_at IS NULL AND is_hidden = false;

ALTER TABLE public.notice_target ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notice_image ENABLE ROW LEVEL SECURITY;

COMMIT;
