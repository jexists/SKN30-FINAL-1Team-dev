-- 팀장의 반려 사유를 담을 자리.
--
-- 0015 를 넣을 때는 기존 report.note 를 쓰려 했는데, 그 칸은 이미 작성자의 것이다.
-- 일일보고서가 "활동 3건 · 첨부 1건" 같은 제 요약을 거기에 넣고 있어서(프론트의
-- useDailyReports.ts), 반려 사유를 같은 칸에 쓰면 작성자가 남긴 값을 덮어쓴다.
--
-- 그래서 검토하는 쪽의 칸을 따로 둔다. reviewed_by_member_id·reviewed_at 과 한 묶음이고,
-- 쓰는 사람은 팀장뿐이다.

BEGIN;

ALTER TABLE public.report
    ADD COLUMN review_note text;

COMMENT ON COLUMN public.report.review_note IS
    '팀장이 반려하며 남긴 사유. 확정하면 비운다. 작성자의 note 와 섞지 않는다.';

COMMIT;
