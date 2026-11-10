# Arnés de inteligencia BI

El chat usa un contrato de ejecución independiente del proveedor: descubrir
metadatos publicados, proponer un plan, validarlo, corregir errores dentro de un
presupuesto y ejecutar únicamente consultas aceptadas. La configuración local
sigue usando **Codex / gpt-5.6-luna**. No hay sustitución automática por un modelo
más potente ni entrenamiento de pesos.

## Componentes

| Responsabilidad | Implementación |
| --- | --- |
| Intención conversacional | `bi_contracts.ChatIntent`, integrado al router del chat; el requisito de datos se deriva del modo. |
| Descubrimiento | `bi_catalog_tools.CatalogTools`: buscar, paginar, leer miembros y relaciones del catálogo autorizado. Incluye definiciones, aliases, dependencias y metadatos semánticos. |
| Plan intermedio | `bi_contracts.Plan`: consultas, aclaración o métrica faltante como resultados mutuamente excluyentes. Normaliza filtros sin cambiar AND/OR. |
| Validación | Contratos de fechas, límites y estructura; compilador existente para miembros, filtros y relaciones; `bi_semantic_validation` para unidades, grano y dimensiones no aditivas declaradas. |
| Conversación | `bi_conversation`: conexión, versión del catálogo, métricas, entidades, filtros y criterio. Descarta el alcance anterior si cambian la conexión o los miembros. Frontend y backend preservan el último estado estructurado. |
| Definición de métricas | `MetricResolution` valida las decisiones del resolutor. Se conserva el circuito de métrica existente, definición incompleta, borrador validable y aprobación desde el menú. El planner no escribe ni publica métricas. |
| Evidencia | Se conservan respuestas numéricas deterministas y recomendaciones con referencias a celdas verificadas. La evidencia añade cobertura, límite alcanzado y truncamiento del snapshot. |
| Recuperación | `bi_runtime.run_planner`: hasta seis llamadas en total, dos oportunidades de corrección y un límite temporal para toda la etapa. Un fallo no se interpreta como prueba de que falta una métrica. |
| Adaptadores | `bi_runtime.complete_json` usa el proveedor configurado en `api.llm`; soporta los adaptadores Codex, Ollama y Gemini existentes. El protocolo de acciones JSON no requiere function calling nativo. |
| Evaluación | `evaluation/evaluate_bi.py` ejecuta casos independientes del modelo sobre catálogos sintéticos, con criterios verificables. |
| Trazabilidad | `bi_trace` registra contrato, prompts, configuración, modelo devuelto, uso de tokens, catálogo, herramientas, planes, evidencia y eventos del chat. `evaluation/replay_bi.py` reproduce la última etapa de planificación de una traza sin llamadas externas. |

## Ejecución y límites

El modelo recibe una vista inicial pequeña y herramientas de solo lectura:
`search_catalog`, `get_members` y `get_relationships`. Las páginas tienen veinte
elementos y devuelven un cursor y el total de coincidencias. Una búsqueda sin
coincidencias no prueba que un concepto esté ausente; el modelo puede buscar
sinónimos y explorar otras páginas. Las claves del plan se validan contra el
catálogo completo, aunque no aparecieran en la vista inicial.

Los contratos rechazan propiedades ejecutables arbitrarias, miembros inexistentes,
fechas inválidas, planes contradictorios y consultas fuera de los límites. Los
errores vuelven al modelo con su ubicación para que corrija el plan. Si no puede
resolverlo dentro del presupuesto, devuelve una aclaración y no ejecuta ni crea.
El tiempo máximo usa la configuración de timeout existente del proveedor
(actualmente 120 segundos para Codex). La clasificación usa esfuerzo bajo;
planificación y resolución de métricas usan esfuerzo medio.

Las validaciones de negocio utilizan metadatos publicados: `unit`, `grain`,
`aggregation` y `non_additive_dimensions`. Una comparación con unidades o granos
declarados distintos requiere una regla validada. Una métrica no aditiva sobre
una dimensión requiere conservar ese corte; un desglose temporal solo se acepta
en su grano nativo declarado o en una fecha exacta. No se infieren unidades,
denominadores ni equivalencias de negocio a partir de un nombre de industria.

Esto no demuestra automáticamente equivalencia entre cualquier concepto y
cualquier fórmula. Las definiciones ausentes o contradictorias siguen necesitando
validación empresarial. Los presupuestos de exploración y contexto son finitos.
Las consultas de la plataforma siguen sujetas a los límites de cada conector.

## Evaluar el modelo configurado

Desde la raíz del repositorio, sin cambiar `.env`:

```powershell
backend/venv/Scripts/python.exe backend/evaluation/evaluate_bi.py --output scratch/bi-evaluation.json
```

El banco incluye asistencia, educación, operaciones, filtros por entidad,
criterios ambiguos, métricas ausentes y descubrimiento en un catálogo grande.
Registra aciertos, aclaraciones innecesarias, detecciones incorrectas de métricas
faltantes, latencia y uso de tokens. Devuelve código de salida distinto de cero
si falla un caso. `--repeats` permite entre una y cinco repeticiones.

Para comparar deliberadamente otro modelo, usar `--provider` y `--model`. Esos
overrides afectan solamente al proceso evaluador; no cambian la plataforma.
`--cases` permite usar el mismo archivo de escenarios con todos los modelos.
No hay precios precargados: `--input-per-million` y `--output-per-million` permiten
una estimación con tarifas proporcionadas por el operador. El uso de la
suscripción de Codex no equivale a facturación por token de la API.

## Trazas y reproducción

`BI_TRACE_DIR` habilita snapshots locales; vacío desactiva su persistencia. La
configuración local quedó habilitada en `backend/runtime/bi-traces`, fuera de Git.
El evaluador utiliza `scratch/bi-traces` por defecto. No se registran encabezados
de autenticación ni razonamiento interno; los snapshots sí contienen preguntas,
metadatos y evidencia de negocio. No se sirven desde endpoints públicos.

```powershell
backend/venv/Scripts/python.exe backend/evaluation/replay_bi.py scratch/bi-traces/ID_DE_TRAZA.json
```

El replay usa las respuestas grabadas, recompone el catálogo y vuelve a validar
el plan. Compara el resultado con el registrado. No vuelve a consultar el LLM ni
las fuentes; tampoco pretende reproducir tiempos o cambios posteriores en datos.
Si una conversación contiene varias etapas de planificación, selecciona la última.
