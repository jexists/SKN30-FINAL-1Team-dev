BEGIN;

CREATE UNIQUE INDEX customer_company_team_name_uq
    ON public.customer_company (team_id, name);

COMMIT;
