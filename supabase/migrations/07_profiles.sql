CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT,
    full_name TEXT,
    title TEXT,
    username TEXT,
    avatar_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS profiles_username_unique_idx
    ON profiles (LOWER(username))
    WHERE username IS NOT NULL AND username <> '';

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'profiles' AND policyname = 'Users can read own profile'
    ) THEN
        CREATE POLICY "Users can read own profile"
        ON profiles
        FOR SELECT
        TO authenticated
        USING ((SELECT auth.uid()) = id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'profiles' AND policyname = 'Users can insert own profile'
    ) THEN
        CREATE POLICY "Users can insert own profile"
        ON profiles
        FOR INSERT
        TO authenticated
        WITH CHECK ((SELECT auth.uid()) = id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'profiles' AND policyname = 'Users can update own profile'
    ) THEN
        CREATE POLICY "Users can update own profile"
        ON profiles
        FOR UPDATE
        TO authenticated
        USING ((SELECT auth.uid()) = id)
        WITH CHECK ((SELECT auth.uid()) = id);
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE ON profiles TO authenticated;

CREATE OR REPLACE FUNCTION set_profiles_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_profiles_updated_at ON profiles;

CREATE TRIGGER set_profiles_updated_at
BEFORE UPDATE ON profiles
FOR EACH ROW
EXECUTE FUNCTION set_profiles_updated_at();
