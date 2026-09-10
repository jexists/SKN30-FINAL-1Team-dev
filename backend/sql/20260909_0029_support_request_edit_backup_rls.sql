-- 백업 표에도 행 수준 보안을 켠다.
--
-- 0028 이 표를 만들면서 이것을 빠뜨렸다. 다른 41개 표는 모두 RLS 가 켜져 있고 정책이
-- 하나도 없다 — 앱은 소유자로 붙어 RLS 를 지나가고, PostgREST 로 들어오는 anon /
-- authenticated 에게는 아무것도 열리지 않는다는 뜻이다. 이 표만 꺼져 있으면 고객불만의
-- 예전 본문이 REST 로 그대로 새어 나간다.
--
-- 0028 은 이미 적용해 두었으므로 고치지 않고 뒤에 붙인다(sql/README.md 변경 원칙 3).

BEGIN;

ALTER TABLE public.support_request_edit_backup ENABLE ROW LEVEL SECURITY;

COMMIT;
