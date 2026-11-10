CREATE TABLE IF NOT EXISTS skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    instruction TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE skills ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'skills' AND policyname = 'Allow read access to skills for everyone'
    ) THEN
        CREATE POLICY "Allow read access to skills for everyone" ON skills FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'skills' AND policyname = 'Allow anyone to insert skills'
    ) THEN
        CREATE POLICY "Allow anyone to insert skills" ON skills FOR INSERT WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'skills' AND policyname = 'Allow anyone to update skills'
    ) THEN
        CREATE POLICY "Allow anyone to update skills" ON skills FOR UPDATE USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'skills' AND policyname = 'Allow anyone to delete skills'
    ) THEN
        CREATE POLICY "Allow anyone to delete skills" ON skills FOR DELETE USING (true);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS skill_agents (
    skill_id UUID REFERENCES skills(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (skill_id, agent_id)
);

ALTER TABLE skill_agents ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'skill_agents' AND policyname = 'Allow read access to skill_agents for everyone'
    ) THEN
        CREATE POLICY "Allow read access to skill_agents for everyone" ON skill_agents FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'skill_agents' AND policyname = 'Allow anyone to manage skill_agents'
    ) THEN
        CREATE POLICY "Allow anyone to manage skill_agents" ON skill_agents FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;
