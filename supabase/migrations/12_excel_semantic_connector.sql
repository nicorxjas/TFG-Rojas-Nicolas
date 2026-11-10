-- Excel semantic connector.
-- Excel uses the provider-neutral semantic catalog and executes through Cube.

CREATE TABLE IF NOT EXISTS public.connectors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key text NOT NULL UNIQUE,
  name text NOT NULL,
  description text NOT NULL DEFAULT '',
  logo_path text,
  section text NOT NULL DEFAULT 'essentials',
  status text NOT NULL DEFAULT 'available',
  sort_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.connectors (key, name, description, logo_path, section, status, sort_order)
VALUES (
  'excel',
  'Excel',
  'Carga workbooks Excel multi-hoja como modelo semantico sobre Cube.',
  '/connectors/excel.png',
  'essentials',
  'available',
  20
)
ON CONFLICT (key) DO UPDATE
SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  logo_path = EXCLUDED.logo_path,
  section = EXCLUDED.section,
  status = EXCLUDED.status,
  sort_order = EXCLUDED.sort_order;

CREATE TABLE IF NOT EXISTS public.connector_instances (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  connector_key text NOT NULL REFERENCES public.connectors(key) ON DELETE RESTRICT,
  provider text NOT NULL DEFAULT 'cube',
  name text NOT NULL DEFAULT '',
  auth_mode text NOT NULL DEFAULT 'legacy',
  status text NOT NULL DEFAULT 'draft',
  is_default boolean NOT NULL DEFAULT false,
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  health jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_sync_at timestamptz,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.connector_instances
  DROP CONSTRAINT IF EXISTS connector_instances_provider_check,
  ADD CONSTRAINT connector_instances_provider_check
    CHECK (provider IN ('powerbi', 'cube'));

ALTER TABLE public.connector_instances
  DROP CONSTRAINT IF EXISTS connector_instances_auth_mode_check,
  ADD CONSTRAINT connector_instances_auth_mode_check
    CHECK (auth_mode IN ('delegated_user', 'service_principal', 'legacy'));

ALTER TABLE public.connector_instances
  DROP CONSTRAINT IF EXISTS connector_instances_status_check,
  ADD CONSTRAINT connector_instances_status_check
    CHECK (status IN ('draft', 'oauth_connected', 'connected', 'syncing', 'ready', 'error', 'disabled'));

CREATE INDEX IF NOT EXISTS connector_instances_owner_idx ON public.connector_instances (owner_user_id, connector_key, status);
CREATE UNIQUE INDEX IF NOT EXISTS connector_instances_owner_default_idx
  ON public.connector_instances (owner_user_id, connector_key)
  WHERE is_default;

CREATE TABLE IF NOT EXISTS public.semantic_models (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  connection_id uuid NOT NULL REFERENCES public.connector_instances(id) ON DELETE CASCADE,
  provider text NOT NULL DEFAULT 'cube',
  external_model_id text NOT NULL,
  workspace_id text,
  dataset_id text,
  name text NOT NULL,
  description text NOT NULL DEFAULT '',
  is_default boolean NOT NULL DEFAULT false,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT semantic_models_connection_external_unique
    UNIQUE (connection_id, external_model_id)
);

ALTER TABLE public.semantic_models
  DROP CONSTRAINT IF EXISTS semantic_models_provider_check,
  ADD CONSTRAINT semantic_models_provider_check
    CHECK (provider IN ('powerbi', 'cube'));

CREATE INDEX IF NOT EXISTS semantic_models_owner_connection_idx ON public.semantic_models (owner_user_id, connection_id);

CREATE TABLE IF NOT EXISTS public.semantic_tables (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  model_id uuid NOT NULL REFERENCES public.semantic_models(id) ON DELETE CASCADE,
  external_table_id text,
  name text NOT NULL,
  display_name text NOT NULL DEFAULT '',
  description text NOT NULL DEFAULT '',
  is_hidden boolean NOT NULL DEFAULT false,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT semantic_tables_model_name_unique UNIQUE (model_id, name)
);

CREATE INDEX IF NOT EXISTS semantic_tables_model_idx ON public.semantic_tables (model_id, is_hidden);

CREATE TABLE IF NOT EXISTS public.semantic_fields (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  model_id uuid NOT NULL REFERENCES public.semantic_models(id) ON DELETE CASCADE,
  table_id uuid REFERENCES public.semantic_tables(id) ON DELETE CASCADE,
  external_field_id text,
  semantic_key text NOT NULL,
  name text NOT NULL,
  display_name text NOT NULL DEFAULT '',
  description text NOT NULL DEFAULT '',
  field_kind text NOT NULL DEFAULT 'dimension',
  data_type text,
  expression text,
  expression_language text,
  format_string text,
  is_hidden boolean NOT NULL DEFAULT false,
  is_sensitive boolean NOT NULL DEFAULT false,
  is_ai_enabled boolean NOT NULL DEFAULT true,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT semantic_fields_model_key_unique
    UNIQUE (model_id, semantic_key)
);

ALTER TABLE public.semantic_fields
  DROP CONSTRAINT IF EXISTS semantic_fields_kind_check,
  ADD CONSTRAINT semantic_fields_kind_check
    CHECK (field_kind IN ('measure', 'dimension', 'time', 'id', 'unknown'));

CREATE INDEX IF NOT EXISTS semantic_fields_model_kind_idx
  ON public.semantic_fields (model_id, field_kind, is_ai_enabled)
  WHERE is_hidden = false;
CREATE INDEX IF NOT EXISTS semantic_fields_owner_key_idx ON public.semantic_fields (owner_user_id, semantic_key);

CREATE TABLE IF NOT EXISTS public.semantic_relationships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  model_id uuid NOT NULL REFERENCES public.semantic_models(id) ON DELETE CASCADE,
  from_table text NOT NULL,
  from_field text NOT NULL,
  to_table text NOT NULL,
  to_field text NOT NULL,
  cardinality text,
  cross_filter_behavior text,
  is_active boolean NOT NULL DEFAULT true,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS semantic_relationships_model_idx ON public.semantic_relationships (model_id, is_active);

CREATE TABLE IF NOT EXISTS public.semantic_sync_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  connection_id uuid NOT NULL REFERENCES public.connector_instances(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'running',
  scan_id text,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  error_message text,
  counters jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

ALTER TABLE public.semantic_sync_runs
  DROP CONSTRAINT IF EXISTS semantic_sync_runs_status_check,
  ADD CONSTRAINT semantic_sync_runs_status_check
    CHECK (status IN ('running', 'success', 'failed'));

CREATE INDEX IF NOT EXISTS semantic_sync_runs_connection_idx ON public.semantic_sync_runs (connection_id, started_at DESC);

CREATE TABLE IF NOT EXISTS public.semantic_aliases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  model_id uuid NOT NULL REFERENCES public.semantic_models(id) ON DELETE CASCADE,
  semantic_key text NOT NULL,
  entity_type text NOT NULL DEFAULT 'field',
  alias text NOT NULL,
  normalized_alias text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT semantic_aliases_unique UNIQUE (model_id, normalized_alias, entity_type)
);

ALTER TABLE public.semantic_aliases
  DROP CONSTRAINT IF EXISTS semantic_aliases_entity_type_check,
  ADD CONSTRAINT semantic_aliases_entity_type_check
    CHECK (entity_type IN ('field', 'measure', 'table'));

CREATE INDEX IF NOT EXISTS semantic_aliases_owner_model_idx ON public.semantic_aliases (owner_user_id, model_id);

ALTER TABLE public.connector_instances ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.semantic_models ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.semantic_tables ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.semantic_fields ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.semantic_relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.semantic_sync_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.semantic_aliases ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'connector_instances' AND policyname = 'Users can read own connector instances') THEN
    CREATE POLICY "Users can read own connector instances"
      ON public.connector_instances FOR SELECT TO authenticated
      USING ((select auth.uid()) = owner_user_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'connector_instances' AND policyname = 'Users can update own connector instances') THEN
    CREATE POLICY "Users can update own connector instances"
      ON public.connector_instances FOR UPDATE TO authenticated
      USING ((select auth.uid()) = owner_user_id)
      WITH CHECK ((select auth.uid()) = owner_user_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'connector_instances' AND policyname = 'Users can delete own connector instances') THEN
    CREATE POLICY "Users can delete own connector instances"
      ON public.connector_instances FOR DELETE TO authenticated
      USING ((select auth.uid()) = owner_user_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'semantic_models' AND policyname = 'Users can read own semantic models') THEN
    CREATE POLICY "Users can read own semantic models"
      ON public.semantic_models FOR SELECT TO authenticated
      USING ((select auth.uid()) = owner_user_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'semantic_tables' AND policyname = 'Users can read own semantic tables') THEN
    CREATE POLICY "Users can read own semantic tables"
      ON public.semantic_tables FOR SELECT TO authenticated
      USING ((select auth.uid()) = owner_user_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'semantic_fields' AND policyname = 'Users can read own semantic fields') THEN
    CREATE POLICY "Users can read own semantic fields"
      ON public.semantic_fields FOR SELECT TO authenticated
      USING ((select auth.uid()) = owner_user_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'semantic_relationships' AND policyname = 'Users can read own semantic relationships') THEN
    CREATE POLICY "Users can read own semantic relationships"
      ON public.semantic_relationships FOR SELECT TO authenticated
      USING ((select auth.uid()) = owner_user_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'semantic_sync_runs' AND policyname = 'Users can read own semantic sync runs') THEN
    CREATE POLICY "Users can read own semantic sync runs"
      ON public.semantic_sync_runs FOR SELECT TO authenticated
      USING ((select auth.uid()) = owner_user_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'semantic_aliases' AND policyname = 'Users can read own semantic aliases') THEN
    CREATE POLICY "Users can read own semantic aliases"
      ON public.semantic_aliases FOR SELECT TO authenticated
      USING ((select auth.uid()) = owner_user_id);
  END IF;
END $$;

GRANT SELECT, UPDATE, DELETE ON public.connector_instances TO authenticated;
GRANT SELECT ON public.semantic_models TO authenticated;
GRANT SELECT ON public.semantic_tables TO authenticated;
GRANT SELECT ON public.semantic_fields TO authenticated;
GRANT SELECT ON public.semantic_relationships TO authenticated;
GRANT SELECT ON public.semantic_sync_runs TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.semantic_aliases TO authenticated;
