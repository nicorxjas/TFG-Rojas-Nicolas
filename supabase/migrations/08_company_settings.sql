CREATE TABLE IF NOT EXISTS company_settings (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    company_name TEXT,
    sector TEXT,
    details TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE company_settings ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'company_settings' AND policyname = 'Users can read own company settings'
    ) THEN
        CREATE POLICY "Users can read own company settings"
        ON company_settings
        FOR SELECT
        TO authenticated
        USING ((SELECT auth.uid()) = id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'company_settings' AND policyname = 'Users can insert own company settings'
    ) THEN
        CREATE POLICY "Users can insert own company settings"
        ON company_settings
        FOR INSERT
        TO authenticated
        WITH CHECK ((SELECT auth.uid()) = id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'company_settings' AND policyname = 'Users can update own company settings'
    ) THEN
        CREATE POLICY "Users can update own company settings"
        ON company_settings
        FOR UPDATE
        TO authenticated
        USING ((SELECT auth.uid()) = id)
        WITH CHECK ((SELECT auth.uid()) = id);
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE ON company_settings TO authenticated;

CREATE OR REPLACE FUNCTION set_company_settings_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_company_settings_updated_at ON company_settings;

CREATE TRIGGER set_company_settings_updated_at
BEFORE UPDATE ON company_settings
FOR EACH ROW
EXECUTE FUNCTION set_company_settings_updated_at();
