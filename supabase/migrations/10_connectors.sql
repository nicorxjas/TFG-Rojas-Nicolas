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

ALTER TABLE public.connectors
  ADD COLUMN IF NOT EXISTS key text,
  ADD COLUMN IF NOT EXISTS name text,
  ADD COLUMN IF NOT EXISTS description text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS logo_path text,
  ADD COLUMN IF NOT EXISTS section text NOT NULL DEFAULT 'essentials',
  ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'available',
  ADD COLUMN IF NOT EXISTS sort_order integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'connectors_status_check'
      AND conrelid = 'public.connectors'::regclass
  ) THEN
    ALTER TABLE public.connectors
      ADD CONSTRAINT connectors_status_check
      CHECK (status IN ('available', 'coming_soon', 'disabled'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS connectors_section_sort_order_idx
  ON public.connectors (section, sort_order);

CREATE OR REPLACE FUNCTION public.set_connectors_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_connectors_updated_at ON public.connectors;
CREATE TRIGGER set_connectors_updated_at
BEFORE UPDATE ON public.connectors
FOR EACH ROW
EXECUTE FUNCTION public.set_connectors_updated_at();

ALTER TABLE public.connectors ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Authenticated users can read connectors" ON public.connectors;
CREATE POLICY "Authenticated users can read connectors"
  ON public.connectors FOR SELECT
  TO authenticated
  USING (true);

GRANT SELECT ON public.connectors TO authenticated;

INSERT INTO public.connectors (key, name, description, logo_path, section, sort_order)
VALUES
  ('powerbi', 'PowerBI', 'Conecta dashboards y reportes de PowerBI con los flujos de Nyro.', '/connectors/powerbi.png', 'essentials', 10),
  ('excel', 'Excel', 'Importa, sincroniza y analiza archivos de Excel desde tus procesos operativos.', '/connectors/excel.png', 'essentials', 20),
  ('google-sheets', 'Google Sheets', 'Conecta hojas de calculo colaborativas para alimentar analisis y reportes.', '/connectors/google-sheets.png', 'essentials', 30)
ON CONFLICT (key) DO UPDATE
SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  logo_path = EXCLUDED.logo_path,
  section = EXCLUDED.section,
  sort_order = EXCLUDED.sort_order;
