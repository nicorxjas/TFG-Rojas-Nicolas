-- Semantic onboarding review state for Excel/GOLD flat-file catalogs.

alter table public.connector_instances
drop constraint if exists connector_instances_status_check;

alter table public.connector_instances
add constraint connector_instances_status_check
check (status in ('draft', 'oauth_connected', 'connected', 'syncing', 'review', 'ready', 'error', 'disabled'));

alter table public.connector_instances
drop constraint if exists connector_instances_auth_mode_check;

alter table public.connector_instances
add constraint connector_instances_auth_mode_check
check (auth_mode in ('delegated_user', 'service_principal', 'legacy', 'connector'));

alter table public.semantic_tables
add column if not exists business_name text not null default '',
add column if not exists suggested_business_name text,
add column if not exists suggested_description text,
add column if not exists approval_status text not null default 'approved',
add column if not exists approved_at timestamptz,
add column if not exists approved_by uuid references auth.users(id) on delete set null;

alter table public.semantic_tables
drop constraint if exists semantic_tables_approval_status_check;

alter table public.semantic_tables
add constraint semantic_tables_approval_status_check
check (approval_status in ('review', 'approved', 'rejected'));

alter table public.semantic_fields
add column if not exists business_name text not null default '',
add column if not exists suggested_business_name text,
add column if not exists suggested_description text,
add column if not exists approval_status text not null default 'approved',
add column if not exists approved_at timestamptz,
add column if not exists approved_by uuid references auth.users(id) on delete set null;

alter table public.semantic_fields
drop constraint if exists semantic_fields_approval_status_check;

alter table public.semantic_fields
add constraint semantic_fields_approval_status_check
check (approval_status in ('review', 'approved', 'rejected'));

update public.semantic_tables
set
  business_name = coalesce(nullif(business_name, ''), nullif(display_name, ''), name),
  approval_status = coalesce(nullif(approval_status, ''), 'approved'),
  approved_at = coalesce(approved_at, updated_at, created_at)
where business_name = ''
  or approval_status is null
  or approval_status = ''
  or approved_at is null;

update public.semantic_fields
set
  business_name = coalesce(nullif(business_name, ''), nullif(display_name, ''), name),
  approval_status = coalesce(nullif(approval_status, ''), 'approved'),
  approved_at = coalesce(approved_at, updated_at, created_at)
where business_name = ''
  or approval_status is null
  or approval_status = ''
  or approved_at is null;

create index if not exists semantic_tables_onboarding_idx
on public.semantic_tables(owner_user_id, model_id, approval_status)
where is_hidden = false;

create index if not exists semantic_fields_onboarding_idx
on public.semantic_fields(owner_user_id, model_id, approval_status)
where is_hidden = false;
