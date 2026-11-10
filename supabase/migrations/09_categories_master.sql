CREATE TABLE IF NOT EXISTS public.categories (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  slug text,
  icon_type text NOT NULL DEFAULT 'icon',
  icon_name text NOT NULL DEFAULT 'tags',
  icon_color text NOT NULL DEFAULT '#d4d4d8',
  icon_emoji text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.categories
  ADD COLUMN IF NOT EXISTS slug text,
  ADD COLUMN IF NOT EXISTS icon_type text NOT NULL DEFAULT 'icon',
  ADD COLUMN IF NOT EXISTS icon_name text NOT NULL DEFAULT 'tags',
  ADD COLUMN IF NOT EXISTS icon_color text NOT NULL DEFAULT '#d4d4d8',
  ADD COLUMN IF NOT EXISTS icon_emoji text,
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'categories_icon_type_check'
      AND conrelid = 'public.categories'::regclass
  ) THEN
    ALTER TABLE public.categories
      ADD CONSTRAINT categories_icon_type_check
      CHECK (icon_type IN ('icon', 'emoji'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS categories_name_idx
  ON public.categories (name);

CREATE OR REPLACE FUNCTION public.set_categories_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_categories_updated_at ON public.categories;
CREATE TRIGGER set_categories_updated_at
BEFORE UPDATE ON public.categories
FOR EACH ROW
EXECUTE FUNCTION public.set_categories_updated_at();

ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Authenticated users can read categories" ON public.categories;
CREATE POLICY "Authenticated users can read categories"
  ON public.categories FOR SELECT
  TO authenticated
  USING (true);

DROP POLICY IF EXISTS "Authenticated users can manage categories" ON public.categories;
CREATE POLICY "Authenticated users can manage categories"
  ON public.categories FOR ALL
  TO authenticated
  USING (true)
  WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.categories TO authenticated;

INSERT INTO public.categories (name, slug, icon_type, icon_name, icon_color)
SELECT seed.name, seed.slug, seed.icon_type, seed.icon_name, seed.icon_color
FROM (VALUES
  ('Stock', 'stock', 'icon', 'package', '#fb923c'),
  ('Operaciones', 'operaciones', 'icon', 'settings', '#22b8cf'),
  ('Ventas', 'ventas', 'icon', 'shopping-cart', '#f472b6'),
  ('Clientes', 'clientes', 'icon', 'users', '#818cf8'),
  ('Finanzas', 'finanzas', 'icon', 'dollar-sign', '#34d399'),
  ('Churn', 'churn', 'icon', 'trending-down', '#fb7185'),
  ('Oportunidad', 'oportunidad', 'icon', 'trending-up', '#38bdf8'),
  ('Riesgos', 'riesgos', 'icon', 'alert-triangle', '#fbbf24'),
  ('General', 'general', 'icon', 'bot', '#d4d4d8')
) AS seed(name, slug, icon_type, icon_name, icon_color)
WHERE NOT EXISTS (
  SELECT 1
  FROM public.categories category
  WHERE category.slug = seed.slug
    OR lower(category.name) = lower(seed.name)
);
