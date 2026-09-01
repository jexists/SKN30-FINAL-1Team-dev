-- 0013의 일정 대표 딜 백필이 기존 통합보고서의 선택 딜과 다르면 연결만 해제한다.
-- 본문/선택 딜 목록은 보존하고, 새 딜별 보고서(content.sales_deal)는 변경하지 않는다.
BEGIN;

UPDATE public.report AS report
SET sales_deal_id = NULL
WHERE report.report_kind = 'meeting'
  AND report.sales_deal_id IS NOT NULL
  AND report.content -> 'sales_deal' IS NULL
  AND jsonb_typeof(report.content -> 'sales_deal_ids') = 'array'
  AND report.content -> 'sales_deal_ids' <> jsonb_build_array(report.sales_deal_id::text);

COMMIT;
