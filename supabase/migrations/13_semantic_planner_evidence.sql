CREATE TABLE IF NOT EXISTS public.analysis_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  connection_id uuid REFERENCES public.connector_instances(id) ON DELETE SET NULL,
  report_id uuid REFERENCES public.reports(id) ON DELETE SET NULL,
  agent_id uuid REFERENCES public.agents(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'running',
  prompt text NOT NULL DEFAULT '',
  plan_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence_count integer NOT NULL DEFAULT 0,
  error_log text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.analysis_runs
  DROP CONSTRAINT IF EXISTS analysis_runs_status_check,
  ADD CONSTRAINT analysis_runs_status_check
    CHECK (status IN ('running', 'success', 'failed'));

CREATE INDEX IF NOT EXISTS analysis_runs_owner_idx ON public.analysis_runs (owner_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS analysis_runs_report_idx ON public.analysis_runs (report_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.analysis_evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_run_id uuid NOT NULL REFERENCES public.analysis_runs(id) ON DELETE CASCADE,
  evidence_key text NOT NULL,
  label text NOT NULL DEFAULT '',
  query_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  compiled_query jsonb,
  result_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  row_count integer NOT NULL DEFAULT 0,
  fingerprint text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS analysis_evidence_run_idx ON public.analysis_evidence (analysis_run_id, created_at);
CREATE INDEX IF NOT EXISTS analysis_evidence_key_idx ON public.analysis_evidence (evidence_key);

CREATE TABLE IF NOT EXISTS public.report_agent_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id uuid REFERENCES public.reports(id) ON DELETE CASCADE,
  agent_id uuid REFERENCES public.agents(id) ON DELETE SET NULL,
  analysis_run_id uuid REFERENCES public.analysis_runs(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'success',
  tool_trace jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_keys text[] NOT NULL DEFAULT ARRAY[]::text[],
  claims jsonb NOT NULL DEFAULT '[]'::jsonb,
  error_log text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.report_agent_runs
  DROP CONSTRAINT IF EXISTS report_agent_runs_status_check,
  ADD CONSTRAINT report_agent_runs_status_check
    CHECK (status IN ('running', 'success', 'failed'));

CREATE INDEX IF NOT EXISTS report_agent_runs_report_idx ON public.report_agent_runs (report_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.semantic_metric_drafts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  connection_id uuid REFERENCES public.connector_instances(id) ON DELETE SET NULL,
  name text NOT NULL,
  description text NOT NULL DEFAULT '',
  expression jsonb NOT NULL DEFAULT '{}'::jsonb,
  compiled_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  dependencies text[] NOT NULL DEFAULT ARRAY[]::text[],
  status text NOT NULL DEFAULT 'draft',
  created_by_ai boolean NOT NULL DEFAULT true,
  source_prompt text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT semantic_metric_drafts_name_not_blank CHECK (length(trim(name)) > 0)
);

ALTER TABLE public.semantic_metric_drafts
  DROP CONSTRAINT IF EXISTS semantic_metric_drafts_status_check,
  ADD CONSTRAINT semantic_metric_drafts_status_check
    CHECK (status IN ('draft', 'approved', 'rejected'));

CREATE INDEX IF NOT EXISTS semantic_metric_drafts_owner_idx ON public.semantic_metric_drafts (owner_user_id, status, created_at DESC);

ALTER TABLE public.analysis_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.analysis_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.report_agent_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.semantic_metric_drafts ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'analysis_runs' AND policyname = 'Users can view own analysis runs') THEN
    CREATE POLICY "Users can view own analysis runs"
      ON public.analysis_runs FOR SELECT TO authenticated
      USING ((select auth.uid()) = owner_user_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'analysis_runs' AND policyname = 'Users can insert own analysis runs') THEN
    CREATE POLICY "Users can insert own analysis runs"
      ON public.analysis_runs FOR INSERT TO authenticated
      WITH CHECK ((select auth.uid()) = owner_user_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'analysis_runs' AND policyname = 'Users can update own analysis runs') THEN
    CREATE POLICY "Users can update own analysis runs"
      ON public.analysis_runs FOR UPDATE TO authenticated
      USING ((select auth.uid()) = owner_user_id)
      WITH CHECK ((select auth.uid()) = owner_user_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'analysis_runs' AND policyname = 'Users can delete own analysis runs') THEN
    CREATE POLICY "Users can delete own analysis runs"
      ON public.analysis_runs FOR DELETE TO authenticated
      USING ((select auth.uid()) = owner_user_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'analysis_evidence' AND policyname = 'Users can view evidence from own runs') THEN
    CREATE POLICY "Users can view evidence from own runs"
      ON public.analysis_evidence FOR SELECT TO authenticated
      USING (
        EXISTS (
          SELECT 1
          FROM public.analysis_runs ar
          WHERE ar.id = analysis_evidence.analysis_run_id
            AND ar.owner_user_id = (select auth.uid())
        )
      );
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'analysis_evidence' AND policyname = 'Users can insert evidence into own runs') THEN
    CREATE POLICY "Users can insert evidence into own runs"
      ON public.analysis_evidence FOR INSERT TO authenticated
      WITH CHECK (
        EXISTS (
          SELECT 1
          FROM public.analysis_runs ar
          WHERE ar.id = analysis_evidence.analysis_run_id
            AND ar.owner_user_id = (select auth.uid())
        )
      );
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'report_agent_runs' AND policyname = 'Users can view own report agent runs') THEN
    CREATE POLICY "Users can view own report agent runs"
      ON public.report_agent_runs FOR SELECT TO authenticated
      USING (
        EXISTS (
          SELECT 1
          FROM public.reports r
          WHERE r.id = report_agent_runs.report_id
            AND r.user_id = (select auth.uid())
        )
      );
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'semantic_metric_drafts' AND policyname = 'Users can view own metric drafts') THEN
    CREATE POLICY "Users can view own metric drafts"
      ON public.semantic_metric_drafts FOR SELECT TO authenticated
      USING ((select auth.uid()) = owner_user_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'semantic_metric_drafts' AND policyname = 'Users can insert own metric drafts') THEN
    CREATE POLICY "Users can insert own metric drafts"
      ON public.semantic_metric_drafts FOR INSERT TO authenticated
      WITH CHECK ((select auth.uid()) = owner_user_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'semantic_metric_drafts' AND policyname = 'Users can update own metric drafts') THEN
    CREATE POLICY "Users can update own metric drafts"
      ON public.semantic_metric_drafts FOR UPDATE TO authenticated
      USING ((select auth.uid()) = owner_user_id)
      WITH CHECK ((select auth.uid()) = owner_user_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'semantic_metric_drafts' AND policyname = 'Users can delete own metric drafts') THEN
    CREATE POLICY "Users can delete own metric drafts"
      ON public.semantic_metric_drafts FOR DELETE TO authenticated
      USING ((select auth.uid()) = owner_user_id);
  END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.analysis_runs TO authenticated;
GRANT SELECT, INSERT ON public.analysis_evidence TO authenticated;
GRANT SELECT ON public.report_agent_runs TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.semantic_metric_drafts TO authenticated;
