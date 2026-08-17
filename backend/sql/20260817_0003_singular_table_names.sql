BEGIN;

ALTER TABLE public.teams RENAME TO team;
ALTER TABLE public.members RENAME TO member;
ALTER TABLE public.customer_companies RENAME TO customer_company;
ALTER TABLE public.customer_contacts RENAME TO customer_contact;
ALTER TABLE public.products RENAME TO product;
ALTER TABLE public.notices RENAME TO notice;
ALTER TABLE public.activities RENAME TO activity;
ALTER TABLE public.activity_companions RENAME TO activity_companion;
ALTER TABLE public.support_requests RENAME TO support_request;
ALTER TABLE public.support_responses RENAME TO support_response;
ALTER TABLE public.pipeline_stages RENAME TO pipeline_stage;
ALTER TABLE public.contracts RENAME TO contract;
ALTER TABLE public.orders RENAME TO purchase_order;
ALTER TABLE public.order_items RENAME TO purchase_order_item;
ALTER TABLE public.sales_targets RENAME TO sales_target;
ALTER TABLE public.reports RENAME TO report;
ALTER TABLE public.report_activities RENAME TO report_activity;
ALTER TABLE public.documents RENAME TO document;
ALTER TABLE public.files RENAME TO file;
ALTER TABLE public.agent_runs RENAME TO agent_run;

COMMIT;
