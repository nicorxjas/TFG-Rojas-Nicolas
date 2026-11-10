DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'semantic_metric_status') THEN
        CREATE TYPE semantic_metric_status AS ENUM ('draft', 'active', 'archived');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS semantic_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    name VARCHAR(160) NOT NULL,
    slug VARCHAR(180) NOT NULL,
    metric_key VARCHAR(220) NOT NULL,
    description TEXT DEFAULT '',
    expression TEXT NOT NULL,
    compiled_expression TEXT NOT NULL,
    variables JSONB NOT NULL DEFAULT '{}'::jsonb,
    dependencies TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    cube_dependencies TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    format VARCHAR(40) NOT NULL DEFAULT 'number',
    status semantic_metric_status NOT NULL DEFAULT 'draft',
    created_by_ai BOOLEAN NOT NULL DEFAULT FALSE,
    approved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT semantic_metrics_slug_user_unique UNIQUE (user_id, slug),
    CONSTRAINT semantic_metrics_key_user_unique UNIQUE (user_id, metric_key),
    CONSTRAINT semantic_metrics_expression_not_blank CHECK (length(trim(expression)) > 0),
    CONSTRAINT semantic_metrics_name_not_blank CHECK (length(trim(name)) > 0)
);

CREATE INDEX IF NOT EXISTS semantic_metrics_user_status_idx ON semantic_metrics (user_id, status);
CREATE INDEX IF NOT EXISTS semantic_metrics_metric_key_idx ON semantic_metrics (metric_key);

ALTER TABLE semantic_metrics ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'semantic_metrics' AND policyname = 'Users can view their own semantic metrics') THEN
        CREATE POLICY "Users can view their own semantic metrics" ON semantic_metrics
            FOR SELECT
            TO authenticated
            USING ((select auth.uid()) = user_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'semantic_metrics' AND policyname = 'Users can insert their own semantic metrics') THEN
        CREATE POLICY "Users can insert their own semantic metrics" ON semantic_metrics
            FOR INSERT
            TO authenticated
            WITH CHECK ((select auth.uid()) = user_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'semantic_metrics' AND policyname = 'Users can update their own semantic metrics') THEN
        CREATE POLICY "Users can update their own semantic metrics" ON semantic_metrics
            FOR UPDATE
            TO authenticated
            USING ((select auth.uid()) = user_id)
            WITH CHECK ((select auth.uid()) = user_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'semantic_metrics' AND policyname = 'Users can delete their own semantic metrics') THEN
        CREATE POLICY "Users can delete their own semantic metrics" ON semantic_metrics
            FOR DELETE
            TO authenticated
            USING ((select auth.uid()) = user_id);
    END IF;
END $$;
