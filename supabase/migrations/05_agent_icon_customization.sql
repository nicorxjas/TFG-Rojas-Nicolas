ALTER TABLE agents ADD COLUMN IF NOT EXISTS icon_type VARCHAR(16) DEFAULT 'icon';
ALTER TABLE agents ADD COLUMN IF NOT EXISTS icon_name VARCHAR(100);
ALTER TABLE agents ADD COLUMN IF NOT EXISTS icon_color VARCHAR(32);
ALTER TABLE agents ADD COLUMN IF NOT EXISTS icon_emoji TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'agents_icon_type_check'
  ) THEN
    ALTER TABLE agents
      ADD CONSTRAINT agents_icon_type_check
      CHECK (icon_type IN ('icon', 'emoji'))
      NOT VALID;
  END IF;
END $$;
