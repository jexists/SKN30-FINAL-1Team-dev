-- 활동에서 '업무'(task) 를 없앤다.
--
-- 일정 등록 화면이 단순해지면서 새 활동은 전부 미팅으로만 만들어진다. 만들 수 없는 타입이
-- 조회와 집계에만 남아 있으면 목록에는 옛 업무가 섞여 나오고, 미팅만 세는 카드와 전 타입을
-- 세는 카드가 서로 어긋난다. 그래서 타입 구분 자체를 지운다.
--
-- 남은 업무 행은 살려 둘 곳이 없다. 붙일 카테고리('내부업무')를 함께 지우기 때문이다.
-- activity 를 가리키는 세 곳 중 cascade 는 activity_companion 하나뿐이라, 나머지 둘을
-- 먼저 정리한 뒤 삭제한다. report 의 참조는 보고서 자체를 지우지 않고 끊기만 한다.

BEGIN;

CREATE TEMP TABLE dropped_activity ON COMMIT DROP AS
SELECT id FROM public.activity WHERE activity_type = 'task';

DELETE FROM public.report_activity
    WHERE activity_id IN (SELECT id FROM dropped_activity);

UPDATE public.report
    SET source_activity_id = NULL
    WHERE source_activity_id IN (SELECT id FROM dropped_activity);

-- activity_companion 은 ON DELETE CASCADE 라 함께 사라진다.
DELETE FROM public.activity
    WHERE id IN (SELECT id FROM dropped_activity);

-- 주간점검·월간점검·분기점검·OJT. 내부회의와 컨퍼런스는 미팅 태그라 그대로 둔다.
DELETE FROM public.activity_action_tag WHERE activity_type = 'task';

-- '내부업무' 카테고리. 위에서 참조하던 활동을 모두 지웠으므로 남은 참조가 없다.
DELETE FROM public.activity_category WHERE activity_type = 'task';

-- 인라인 CHECK 라 컬럼과 함께 사라진다.
ALTER TABLE public.activity DROP COLUMN activity_type;
ALTER TABLE public.activity_category DROP COLUMN activity_type;
ALTER TABLE public.activity_action_tag DROP COLUMN activity_type;

COMMIT;
