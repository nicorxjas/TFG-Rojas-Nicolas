-- Migration 03: Add blocks column to report_templates
ALTER TABLE report_templates ADD COLUMN IF NOT EXISTS blocks JSONB DEFAULT '[]'::jsonb;

-- Migrate existing seed templates to have default blocks representing their structure
UPDATE report_templates 
SET blocks = '[
  {
    "id": "block-title-1",
    "type": "title",
    "content": {
      "text": "Resumen Semanal de Ventas",
      "level": "h1"
    }
  },
  {
    "id": "block-pred-1",
    "type": "predictive",
    "content": {
      "description": "Análisis Interpretativo y Sugerencias de Negocio",
      "prompt": "Eres un analista financiero. Analiza el siguiente set de datos de ventas de la última semana y genera un resumen ejecutivo. Destaca tendencias clave y sugiere 2 acciones concretas para aumentar el ticket promedio. Responde estrictamente en formato JSON con la estructura solicitada."
    }
  },
  {
    "id": "block-table-1",
    "type": "table",
    "content": {
      "title": "Métricas clave de Ventas"
    }
  },
  {
    "id": "block-chart-1",
    "type": "chart",
    "content": {
      "title": "Evolución de Facturación y Operaciones",
      "chartType": "line"
    }
  }
]'::jsonb
WHERE name LIKE '%Ventas%';

UPDATE report_templates 
SET blocks = '[
  {
    "id": "block-title-2",
    "type": "title",
    "content": {
      "text": "Desempeño por Rubro",
      "level": "h1"
    }
  },
  {
    "id": "block-pred-2",
    "type": "predictive",
    "content": {
      "description": "Análisis de Rentabilidad y Volúmenes de Venta",
      "prompt": "Eres un gerente de producto. Revisa los datos adjuntos que contienen las ventas y unidades vendidas agrupadas por rubro. Crea un resumen ejecutivo resaltando qué rubro es el más rentable y cuál tiene mayor volumen. Sugiere 2 acciones operativas. Formato JSON obligatorio."
    }
  },
  {
    "id": "block-table-2",
    "type": "table",
    "content": {
      "title": "Desempeño Comercial por Rubro Principal"
    }
  },
  {
    "id": "block-chart-2",
    "type": "chart",
    "content": {
      "title": "Distribución Facturación por Rubro",
      "chartType": "bar"
    }
  }
]'::jsonb
WHERE name LIKE '%Rubro%';
