-- 미팅 한 건에서 여러 딜을 다룰 수 있으므로, 보고서 한 행은 그중 한 딜을 가리킨다.
-- 기존 단일 딜 일정은 그 연결을 승계하고, 나머지 기존 보고서는 NULL을 유지한다.
BEGIN;

ALTER TABLE public.report
    ADD COLUMN sales_deal_id uuid REFERENCES public.sales_deal (id);

UPDATE public.report AS report
SET sales_deal_id = activity.sales_deal_id
FROM public.activity AS activity
WHERE report.report_kind = 'meeting'
  AND report.source_activity_id = activity.id
  AND activity.sales_deal_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM public.report AS other
      WHERE other.source_activity_id = report.source_activity_id AND other.id <> report.id
  );

CREATE UNIQUE INDEX report_source_activity_sales_deal_key
    ON public.report (source_activity_id, sales_deal_id)
    WHERE source_activity_id IS NOT NULL AND sales_deal_id IS NOT NULL;

CREATE INDEX report_sales_deal_date_idx
    ON public.report (sales_deal_id, report_date DESC)
    WHERE sales_deal_id IS NOT NULL;

COMMENT ON COLUMN public.report.sales_deal_id IS
    '미팅보고서가 다루는 딜. 기존 보고서와 미팅 외 보고서는 NULL을 허용한다.';

COMMIT;
