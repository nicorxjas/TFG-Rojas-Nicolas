-- 1. Definición del ciclo de vida del informe
CREATE TYPE report_status AS ENUM ('PENDING', 'GENERATING', 'SUCCESS', 'FAILED');

-- 2. Tabla de moldes/templates de informes
CREATE TABLE report_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    system_prompt TEXT NOT NULL,
    cube_query_config JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Habilitar RLS y políticas para report_templates (Todos pueden leer)
ALTER TABLE report_templates ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow read access to everyone" ON report_templates FOR SELECT USING (true);

-- 3. Tabla de informes generados
CREATE TABLE reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID REFERENCES report_templates(id) ON DELETE SET NULL,
    user_id UUID NOT NULL, -- UUID de Supabase Auth
    status report_status DEFAULT 'PENDING' NOT NULL,
    content JSONB, -- Contenido estructurado: {executive_summary, actionables, chart_data}
    error_log TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Habilitar RLS en la tabla de informes
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;

-- 5. Crear la política de RLS (Los usuarios solo ven y crean sus propios reportes)
CREATE POLICY "Users can view their own reports" ON reports
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own reports" ON reports
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own reports" ON reports
    FOR DELETE USING (auth.uid() = user_id);

-- Opcional para backend (Service Role)
CREATE POLICY "Service Role can do anything" ON reports
    FOR ALL USING (auth.role() = 'service_role');

-- 6. Insertar Templates de Ejemplo (Seed Data)
INSERT INTO report_templates (name, description, system_prompt, cube_query_config) VALUES (
    'Resumen Semanal de Ventas',
    'Un análisis detallado de las ventas, cantidad de operaciones y el ticket promedio de los últimos 7 días.',
    'Eres un analista financiero. Analiza el siguiente set de datos de ventas de la última semana y genera un resumen ejecutivo. Destaca tendencias clave y sugiere 2 acciones concretas para aumentar el ticket promedio. Responde estrictamente en formato JSON con la estructura solicitada.',
    '{"cube_query": {"measures": ["Ventas.monto_total", "Ventas.cantidad_ventas"], "timeDimensions": [{"dimension": "Ventas.fecha", "dateRange": "Last 7 days"}], "dimensions": ["Ventas.fecha"]}, "dynamic_metrics": [{"id": "ticket_promedio", "label": "Ticket Promedio", "formula": "Ventas_monto_total / Ventas_cantidad_ventas", "format": "currency"}]}'
);

INSERT INTO report_templates (name, description, system_prompt, cube_query_config) VALUES (
    'Desempeño por Rubro',
    'Comparativa del monto total facturado y las unidades vendidas discriminado por rubro principal.',
    'Eres un gerente de producto. Revisa los datos adjuntos que contienen las ventas y unidades vendidas agrupadas por rubro. Crea un resumen ejecutivo resaltando qué rubro es el más rentable y cuál tiene mayor volumen. Sugiere 2 acciones operativas. Formato JSON obligatorio.',
    '{"cube_query": {"measures": ["Ventas.monto_total", "Ventas.cantidad_vendida"], "dimensions": ["Productos.Rubro"]}, "dynamic_metrics": []}'
);

-- ==============================================================================
-- INSTRUCCIONES PARA EL WEBHOOK
-- ==============================================================================
-- En el dashboard de Supabase, ve a "Database" -> "Webhooks" y crea un nuevo Webhook.
-- 1. Nombre: Trigger Report Generation
-- 2. Tabla: reports
-- 3. Eventos: INSERT
-- 4. Tipo de Request: HTTP Request
-- 5. Method: POST
-- 6. URL: https://tu-backend-url.com/api/generate-report (reemplaza con tu URL o ngrok)
-- 7. HTTP Headers: Si usas tokens para tu backend, colócalo aquí.
