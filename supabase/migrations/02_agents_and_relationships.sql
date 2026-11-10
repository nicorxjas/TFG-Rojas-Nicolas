-- 1. Tabla de agentes
CREATE TABLE IF NOT EXISTS agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    system_prompt TEXT NOT NULL,
    category VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Habilitar RLS para agentes
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow read access to agents for everyone" ON agents FOR SELECT USING (true);
CREATE POLICY "Allow anyone to insert agents" ON agents FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow anyone to update agents" ON agents FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY "Allow anyone to delete agents" ON agents FOR DELETE USING (true);

-- 2. Habilitar políticas de edición para report_templates si no existen
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'report_templates' AND policyname = 'Allow anyone to insert templates'
    ) THEN
        CREATE POLICY "Allow anyone to insert templates" ON report_templates FOR INSERT WITH CHECK (true);
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'report_templates' AND policyname = 'Allow anyone to update templates'
    ) THEN
        CREATE POLICY "Allow anyone to update templates" ON report_templates FOR UPDATE USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'report_templates' AND policyname = 'Allow anyone to delete templates'
    ) THEN
        CREATE POLICY "Allow anyone to delete templates" ON report_templates FOR DELETE USING (true);
    END IF;
END $$;

-- 3. Tabla de relación muchos-a-muchos: Plantillas -> Agentes
ALTER TABLE report_templates ADD COLUMN IF NOT EXISTS category VARCHAR(100);

CREATE TABLE IF NOT EXISTS template_agents (
    template_id UUID REFERENCES report_templates(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    PRIMARY KEY (template_id, agent_id)
);

ALTER TABLE template_agents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow read access to template_agents for everyone" ON template_agents FOR SELECT USING (true);
CREATE POLICY "Allow anyone to manage template_agents" ON template_agents FOR ALL USING (true);

-- 4. Ampliar tabla reports para soportar personalizaciones
ALTER TABLE reports ADD COLUMN IF NOT EXISTS name VARCHAR(255);
ALTER TABLE reports ADD COLUMN IF NOT EXISTS prompt TEXT;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS include_charts BOOLEAN DEFAULT FALSE;

-- 5. Tabla de relación muchos-a-muchos: Informes -> Agentes
CREATE TABLE IF NOT EXISTS report_agents (
    report_id UUID REFERENCES reports(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    PRIMARY KEY (report_id, agent_id)
);

ALTER TABLE report_agents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow read access to report_agents for everyone" ON report_agents FOR SELECT USING (true);
CREATE POLICY "Allow anyone to manage report_agents" ON report_agents FOR ALL USING (true);

-- 6. Insertar Agentes de Semilla (Seed Data)
INSERT INTO agents (id, name, description, system_prompt, category) VALUES
('1a1a1a1a-1a1a-1a1a-1a1a-1a1a1a1a1a1a', 'Agente Financiero', 'Analiza métricas de ingresos, márgenes, costos y KPIs financieros clave para detectar desvíos y oportunidades.', 'Eres un experto en análisis financiero empresarial. Evalúas los datos de ingresos, costos y márgenes para identificar tendencias, alertas y oportunidades de mejora. Comunica los hallazgos con claridad y precisión.', 'finanzas'),
('2b2b2b2b-2b2b-2b2b-2b2b-2b2b2b2b2b2b', 'Agente de Churn', 'Identifica patrones de cancelación, segmentos en riesgo y factores predictivos de abandono de clientes.', 'Eres un especialista en retención de clientes y análisis de churn. Analizas comportamientos, frecuencia de uso y señales tempranas de abandono para generar insights accionables que reduzcan la tasa de cancelación.', 'churn'),
('3c3c3c3c-3c3c-3c3c-3c3c-3c3c3c3c3c3c', 'Agente de Oportunidades', 'Detecta segmentos de alto potencial, up-sell y cross-sell basados en el comportamiento de compra.', 'Eres un analista de oportunidades comerciales. Tu objetivo es identificar segmentos de clientes con alto potencial de crecimiento, oportunidades de upsell y patrones de compra que permitan generar más valor.', 'oportunidad'),
('4d4d4d4d-4d4d-4d4d-4d4d-4d4d4d4d4d4d', 'Agente de Riesgos', 'Evalúa exposiciones, concentraciones de riesgo y señales de alerta temprana en la cartera de clientes.', 'Eres un experto en gestión de riesgos. Evalúas la concentración de cartera, exposición crediticia, anomalías operativas y señales de alerta que puedan impactar negativamente al negocio.', 'riesgos')
ON CONFLICT (id) DO NOTHING;

-- Asociar plantilla de Ventas con Agente Financiero
INSERT INTO template_agents (template_id, agent_id)
SELECT id, '1a1a1a1a-1a1a-1a1a-1a1a-1a1a1a1a1a1a'::UUID FROM report_templates WHERE name LIKE '%Ventas%'
ON CONFLICT DO NOTHING;

-- Asociar plantilla de Rubro con Agente de Oportunidades
INSERT INTO template_agents (template_id, agent_id)
SELECT id, '3c3c3c3c-3c3c-3c3c-3c3c-3c3c3c3c3c3c'::UUID FROM report_templates WHERE name LIKE '%Rubro%'
ON CONFLICT DO NOTHING;

-- Actualizar categorías de plantillas iniciales
UPDATE report_templates SET category = 'finanzas' WHERE name LIKE '%Ventas%';
UPDATE report_templates SET category = 'oportunidad' WHERE name LIKE '%Rubro%';

