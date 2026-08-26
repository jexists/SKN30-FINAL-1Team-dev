-- 팀당 팀장은 한 명이다.
--
-- 지금까지 이 규칙은 어디에도 적혀 있지 않았다. /admin 계정 발급 화면에서 같은 팀에
-- 팀장을 몇 명이든 만들 수 있었고, 그렇게 되면 팀장 전용 화면(상품 등록 등)의 권한이
-- 누구에게 있는지가 데이터에 따라 달라진다.
--
-- 앱에서도 발급 전에 막지만 근거는 여기에 둔다. 동시에 들어온 두 요청은 앱 검사를
-- 나란히 통과할 수 있고, 그때 남는 것을 막는 것은 인덱스뿐이다.
--
-- active 가 false 인 팀장은 세지 않는다. 물러난 팀장이 후임 발급을 막으면 안 된다.
-- 조회 스코프(deps.active_member)가 active 를 함께 보는 것과 같은 기준이다.

BEGIN;

CREATE UNIQUE INDEX member_one_manager_per_team_uq
    ON public.member (team_id) WHERE role_code = 'manager' AND active;

COMMENT ON INDEX public.member_one_manager_per_team_uq IS
    '팀당 활성 팀장은 한 명. 두 번째 팀장 발급을 DB 에서 막는다.';

COMMIT;
