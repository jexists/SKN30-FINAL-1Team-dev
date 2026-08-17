BEGIN;

CREATE TABLE public.teams (
    id uuid PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name) <> ''),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.members (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.teams (id),
    login_id text NOT NULL UNIQUE CHECK (btrim(login_id) <> '' AND login_id = lower(login_id)),
    password_hash text NOT NULL CHECK (btrim(password_hash) <> ''),
    display_name text NOT NULL CHECK (btrim(display_name) <> ''),
    role_code text NOT NULL CHECK (role_code IN ('member', 'manager')),
    job_title text CHECK (job_title IS NULL OR btrim(job_title) <> ''),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX members_team_active_idx
    ON public.members (team_id, active);

CREATE TABLE public.customer_companies (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.teams (id),
    name text NOT NULL CHECK (btrim(name) <> ''),
    region_code text CHECK (region_code IS NULL OR btrim(region_code) <> ''),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX customer_companies_team_name_idx
    ON public.customer_companies (team_id, name);

CREATE TABLE public.customer_contacts (
    id uuid PRIMARY KEY,
    company_id uuid NOT NULL REFERENCES public.customer_companies (id),
    owner_member_id uuid NOT NULL REFERENCES public.members (id),
    name text NOT NULL CHECK (btrim(name) <> ''),
    department text CHECK (department IS NULL OR btrim(department) <> ''),
    job_title text CHECK (job_title IS NULL OR btrim(job_title) <> ''),
    email text CHECK (email IS NULL OR btrim(email) <> ''),
    phone text NOT NULL CHECK (btrim(phone) <> ''),
    status_code text CHECK (status_code IS NULL OR btrim(status_code) <> ''),
    source_code text CHECK (source_code IS NULL OR btrim(source_code) <> ''),
    memo text CHECK (memo IS NULL OR btrim(memo) <> ''),
    registered_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX customer_contacts_company_name_idx
    ON public.customer_contacts (company_id, name);

CREATE INDEX customer_contacts_owner_idx
    ON public.customer_contacts (owner_member_id);

CREATE TABLE public.activities (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES public.teams (id),
    owner_member_id uuid NOT NULL REFERENCES public.members (id),
    customer_contact_id uuid REFERENCES public.customer_contacts (id),
    end_user_contact_id uuid REFERENCES public.customer_contacts (id),
    activity_type text NOT NULL CHECK (activity_type IN ('meeting', 'task')),
    category_code text NOT NULL CHECK (btrim(category_code) <> ''),
    title text NOT NULL CHECK (btrim(title) <> ''),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz,
    all_day boolean NOT NULL DEFAULT false,
    due_at timestamptz,
    location text CHECK (location IS NULL OR btrim(location) <> ''),
    action_tag text CHECK (action_tag IS NULL OR btrim(action_tag) <> ''),
    completed_at timestamptz,
    note text CHECK (note IS NULL OR btrim(note) <> ''),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT activities_ends_after_start
        CHECK (ends_at IS NULL OR ends_at > starts_at)
);

CREATE INDEX activities_team_starts_idx
    ON public.activities (team_id, starts_at)
    WHERE deleted_at IS NULL;

CREATE INDEX activities_team_owner_starts_idx
    ON public.activities (team_id, owner_member_id, starts_at)
    WHERE deleted_at IS NULL;

CREATE INDEX activities_customer_contact_idx
    ON public.activities (customer_contact_id)
    WHERE customer_contact_id IS NOT NULL AND deleted_at IS NULL;

CREATE TABLE public.activity_companions (
    activity_id uuid NOT NULL REFERENCES public.activities (id) ON DELETE CASCADE,
    member_id uuid NOT NULL REFERENCES public.members (id),
    PRIMARY KEY (activity_id, member_id)
);

CREATE INDEX activity_companions_member_idx
    ON public.activity_companions (member_id);

COMMIT;
