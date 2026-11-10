# Codex App Server para pruebas locales

El chat utiliza el [arnés BI](BI_HARNESS.md), con contratos y evaluación
independientes del proveedor. La configuración de modelo se mantiene.

Configuración activa en `backend/.env`:

```dotenv
LLM_PROVIDER=codex
LLM_MODEL=gpt-5.6-luna
CODEX_REASONING_EFFORT=low
CODEX_TIMEOUT_SECONDS=120
```

Requiere Codex CLI con sesión de ChatGPT (`codex login status`). Detecta el CLI
incluido en Codex Desktop para Windows; `CODEX_EXECUTABLE` permite indicar otro
ejecutable. Reiniciar el backend después de cambiar variables. Un override de
`REPORT_LLM_MODEL` debe nombrar un modelo disponible en Codex.

Luna usa razonamiento bajo por defecto para reducir consumo de cuota y latencia.
El planificador y el resolutor de métricas piden razonamiento medio; el adaptador
respeta `reasoning_effort` por solicitud y usa `CODEX_REASONING_EFFORT` cuando no
se especifica. La clasificación conversacional conserva razonamiento bajo.
Utiliza los límites compartidos de Codex de la suscripción: no es ilimitado ni
utiliza el saldo de la API. No cambia automáticamente a Gemini ni a otro modelo.
No copia tokens OAuth; el CLI administra la autenticación existente.

El adaptador sirve chat, planificación, informes, métricas, onboarding y Excel.
Conserva los prompts y catálogos proporcionados por esas funciones, sin respuestas
ni identificadores de negocio fijados en el adaptador. Las herramientas propuestas
se devuelven al backend para su validación y ejecución habitual.

Cada solicitud abre una conversación efímera sin entorno de trabajo ni herramientas
del equipo. Desactiva los servidores MCP configurados para esa conversación y
rechaza solicitudes de herramientas o permisos. Un proceso persistente serializa
las solicitudes; el tiempo máximo incluye la espera en cola. No está diseñado como
servicio compartido de producción para múltiples usuarios.

La dirección `http://codex-app-server.local/v1` es un identificador interceptado por
el transporte HTTPX: no requiere un servidor HTTP ni un puerto nuevo. La comunicación
real es JSON-RPC por stdio. Las respuestas SSE se entregan al finalizar la generación,
sin streaming de tokens intermedios. `temperature` y `max_tokens` no tienen una
equivalencia aplicada en App Server; el esfuerzo se controla con
`reasoning_effort` de la solicitud o, por defecto, `CODEX_REASONING_EFFORT`.
