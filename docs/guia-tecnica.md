# BI AI · Nyro-App

Plataforma de BI conversacional con chat, agentes, informes y catálogo semántico. Permite conectar un Excel o un modelo de Power BI para consultar datos mediante un LLM.

## Arquitectura y requisitos

| Componente | Función | Ejecución local |
| --- | --- | --- |
| Frontend | Next.js 16, React 19 y autenticación | Node.js, puerto 3000 |
| Backend | FastAPI, conectores, consultas y LLM | Python, puerto 8000 |
| Supabase | Auth, configuración, catálogo e informes | Proyecto configurado por separado |
| Cube + DuckDB | Consultas sobre los CSV generados desde Excel | Docker, puerto 4000 |
| LLM | Interpretación, planificación y respuestas | Codex CLI (configuracion de la demo) |

Requisitos: Git, Node.js **20.9 o superior** con npm, Python **3.11 o superior** y Docker Desktop con Docker Compose para usar Excel. Los comandos siguientes son para **PowerShell en Windows**, desde la raíz del repositorio salvo indicación contraria.

Docker ejecuta **solamente Cube**. No hay Dockerfiles para frontend/backend. El Compose operativo es [`cube/docker-compose.yml`](../cube/docker-compose.yml). PostgreSQL local y Redis no son requisitos del flujo actual: la aplicación usa Supabase.

## 1. Instalar dependencias

Después de clonar el repositorio y entrar en su carpeta:

```powershell
python -m venv backend/venv
./backend/venv/Scripts/python.exe -m pip install -r backend/requirements.txt
npm --prefix frontend ci
```

No hace falta activar el entorno virtual si se utiliza su ejecutable como en estos ejemplos.

## 2. Crear los archivos de entorno

Copiar las plantillas **una sola vez**, sin sobrescribir una configuración local existente:

```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env.local
Copy-Item cube/.env.example cube/.env
```

Completar los archivos de destino. Las plantillas contienen ejemplos sin credenciales reales y se pueden versionar. `.gitignore` excluye `.env`, `.env.local`, variantes `.env.*` y copias; únicamente permite las plantillas `.env.example`. El `.env.example` de la raíz indica dónde está cada plantilla; la aplicación no carga un `.env` de la raíz.

El backend lee `backend/.env`; Next.js lee `frontend/.env.local`; Docker Compose lee `cube/.env`. Reiniciar el proceso correspondiente al cambiar variables. Usar un único valor por variable y no agregar comentarios al final de las líneas de `backend/.env`.

### Frontend: `frontend/.env.local`

| Variable | Valor |
| --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | URL del proyecto Supabase, igual a `SUPABASE_URL` del backend |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Clave pública `anon` del mismo proyecto |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` |

Las variables `NEXT_PUBLIC_*` son visibles en el navegador. **Nunca colocar allí `service_role`, el secreto JWT, contraseñas ni claves del LLM.**

### Backend: `backend/.env`

| Variable | Uso |
| --- | --- |
| `SUPABASE_URL` | URL del proyecto Supabase; obligatoria |
| `SUPABASE_SERVICE_ROLE_KEY` | Clave privada del servidor para acceder a las tablas; obligatoria |
| `SUPABASE_JWT_SECRET` | Secreto para validación HS256 del endpoint de salud protegido |
| `LLM_PROVIDER` | `codex`, `ollama` o `gemini`; ver configuración abajo |
| `LLM_MODEL` | Modelo del proveedor elegido |
| `CUBE_API_URL` | `http://localhost:4000/cubejs-api/v1/load` para Excel |
| `CUBEJS_API_SECRET` | Opcional en desarrollo con `CUBEJS_DEV_MODE=true`; no es un JWT de producción |
| `BI_TRACE_DIR` | Vacío desactiva trazas; usar `backend/runtime/bi-traces` para diagnóstico local |
| `DATABASE_URL` | Opcional: conexión PostgreSQL para scripts auxiliares; la API usa Supabase REST |

La plantilla incluye opciones de proveedores, informes y Power BI. No se requieren `REDIS_URL` ni `ENVIRONMENT` para iniciar el flujo actual.

## 3. Preparar Supabase

1. Crear un proyecto Supabase o usar uno existente autorizado para este entorno.
2. En una **base nueva**, ejecutar los SQL de [`supabase/migrations/`](../supabase/migrations/) en orden numérico, desde `01_reports_schema.sql` hasta `14_semantic_onboarding_review.sql`, desde el SQL Editor. Incluyen tablas, relaciones, políticas, conectores y revisión semántica. En una base existente, aplicar solo las migraciones pendientes: algunos scripts iniciales no son idempotentes.
3. En Auth, configurar la URL del sitio `http://localhost:3000` y permitir el retorno `http://localhost:3000/auth/callback` para los flujos que lo utilicen.
4. Habilitar correo/contraseña y crear un usuario desde `/signup` o desde la administración de Supabase. Si se requiere confirmación de correo, confirmarlo antes de ingresar.
5. Completar las variables del frontend y del backend con los valores del **mismo proyecto**.

El endpoint `/api/health/protected` valida tokens HS256: requiere un token compatible con el secreto configurado. `/api/health/` es público y solo confirma que la API está levantada.

Los informes creados desde la interfaz se procesan desde la API. No hace falta configurar el webhook histórico mencionado en la migración 01 para este flujo.

## 4. Conectar el LLM

La demo utiliza **Codex / gpt-5.6-luna**, configurado en `backend/.env`. `REPORT_LLM_MODEL`, si se configura, también debe existir en ese proveedor; si queda vacío, los informes usan el modelo general.

### Codex CLI

El adaptador usa Codex App Server por stdio y la sesión del CLI. Requiere Codex CLI instalado o disponible a través de Codex Desktop en Windows, con una sesión autorizada:

```powershell
codex login
codex login status
```

```dotenv
LLM_PROVIDER=codex
LLM_MODEL=gpt-5.6-luna
CODEX_REASONING_EFFORT=low
CODEX_TIMEOUT_SECONDS=120
```

`gpt-5.6-luna` es el predeterminado del adaptador del repositorio; si tu sesión no lo ofrece, reemplazarlo por un modelo disponible para ella. Si el CLI no se detecta, configurar `CODEX_EXECUTABLE` con la ruta completa a `codex.exe`. Con esa ruta también se puede ejecutar `& "C:/ruta/codex.exe" login status`.

No requiere `GEMINI_API_KEY`, API key de OpenAI ni un servidor HTTP adicional. El CLI administra sus credenciales fuera del repositorio. Este adaptador está orientado a pruebas locales y serializa las solicitudes. Detalles: [`backend/CODEX_LLM.md`](../backend/CODEX_LLM.md).

## 5. Levantar Cube con Docker

Necesario para consultar el Excel. Abrir Docker Desktop y comprobar que el motor esté activo. La plantilla configura DuckDB, modo de desarrollo y `/data/nyro_analytics.db` como base local dentro del contenedor.

```powershell
docker compose -f cube/docker-compose.yml up -d
docker compose -f cube/docker-compose.yml ps
docker compose -f cube/docker-compose.yml logs --tail 100 cube
```

El contenedor monta `cube/` en `/cube/conf` y `data/` en `/data`. Los modelos generados leen los CSV de `/data/excel/`; no hay que copiar archivos al contenedor. Si `data/nyro_analytics.db` existe se reutiliza; no reemplazarlo mientras está en uso. La imagen es `cubejs/cube:latest`, por lo que una descarga futura puede cambiar la versión.

Cube queda accesible en [http://localhost:4000](http://localhost:4000). `CUBEJS_DEV_MODE=true` es para desarrollo local: no exponerlo directamente a Internet. Para producción hacen falta autenticación de Cube y emisión de JWT; el secreto de firma por sí solo no es un token válido para consumir su API.

Para detener Cube conservando los archivos montados:

```powershell
docker compose -f cube/docker-compose.yml down
```

## 6. Levantar API y frontend

En dos terminales, desde la raíz del repositorio:

```powershell
# Terminal 1: API
./backend/venv/Scripts/python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2: frontend
npm --prefix frontend run dev
```

| Dirección | Uso |
| --- | --- |
| [http://localhost:3000](http://localhost:3000) | Aplicación; ingresar con el usuario de Supabase |
| [http://localhost:8000/docs](http://localhost:8000/docs) | Documentación interactiva de la API |
| [http://localhost:8000/api/health/](http://localhost:8000/api/health/) | Salud pública de la API |
| [http://localhost:4000](http://localhost:4000) | Cube para consultas del Excel |

CORS permite `http://localhost:3000` y `http://127.0.0.1:3000`. Si Next.js cambia de puerto porque el 3000 está ocupado, liberar ese puerto o adaptar CORS y las URLs de autenticación.

## 7. Cargar el Excel de datos

El archivo local es **`data/Datos.xlsx`**. En el equipo de origen está en:

```text
C:\Users\Nico\Documents\1. Second Brain\2. Areas\Nyro\Áreas\Operaciones\Plataforma\Nyro-App\data\Datos.xlsx
```

En otro equipo, colocar una copia autorizada en `data/Datos.xlsx` o seleccionarla desde otra carpeta. Esa ruta absoluta **no está configurada en el código**: guardar el archivo en `data/` no lo importa automáticamente. Los datos locales quedan excluidos de nuevas incorporaciones a Git; si el clon no contiene el Excel, obtenerlo por separado.

El workbook actual contiene estas hojas:

| Hoja | Contenido |
| --- | --- |
| `DIM_Fecha` | Dimensión de fechas |
| `DIM_Cliente` | Dimensión de clientes |
| `DIM_Producto` | Dimensión de productos |
| `DIM_Proveedor` | Dimensión de proveedores |
| `FACT_Inventario_Mensual` | Hechos de inventario mensual |
| `FACT_Ventas` | Hechos de ventas |

Pasos en la aplicación:

1. Iniciar sesión y completar **Configuración → Empresa** (`/settings/empresa`). El conector requiere este contexto antes de procesar.
2. Abrir **Configuración → Conectores** (`/settings/conectores`) y seleccionar **Excel**.
3. Elegir `Datos.xlsx` y pulsar **Procesar workbook**. Acepta `.xlsx` de hasta **25 MB**, con encabezados y filas tabulares.
4. Revisar y aprobar los conceptos, relaciones e indicadores solicitados por el asistente de incorporación. La conexión pasa inicialmente a revisión; terminar el proceso antes de consultar.
5. Verificar el **Modelo semántico** y abrir el chat para consultar los datos.

El backend usa DuckDB y su extensión `excel`. La primera importación puede necesitar Internet para instalar esa extensión. Después genera:

- `data/excel/<connection_id>/*.csv`: exportación de cada hoja.
- `cube/model/Excel_<id>.js`: modelo de Cube para la conexión.
- Catálogo, relaciones y estado de conexión en Supabase.

Los identificadores son propios de cada importación y entorno. Los CSV o modelos de una conexión anterior no sustituyen la carga y aprobación con el usuario actual. Para actualizar datos, volver a procesar el archivo desde el conector. Si Cube no detecta el modelo, revisar logs y ejecutar `docker compose -f cube/docker-compose.yml restart cube`.

## Power BI opcional

No hace falta para probar con Excel. Configurar la aplicación Microsoft Entra desde Conectores o mediante las variables `POWERBI_*` de `backend/.env.example`.

El callback local es `http://localhost:8000/connectors/powerbi/callback` y debe coincidir con la URI registrada en Entra. `API_PUBLIC_BASE_URL` y `FRONTEND_BASE_URL` controlan los retornos. Después de autorizar, seleccionar el modelo, sincronizar y completar la revisión semántica. Usuario y aplicación necesitan permisos sobre ese modelo.

## Verificaciones y problemas frecuentes

```powershell
Invoke-RestMethod http://localhost:8000/api/health/
docker compose -f cube/docker-compose.yml ps
```

La salud debe responder `{"status":"ok"}`. No verifica Supabase, Cube ni el LLM: completar también una carga y una consulta desde la interfaz.

| Problema | Revisar |
| --- | --- |
| Faltan `SUPABASE_URL` o `SUPABASE_SERVICE_ROLE_KEY` | Completar `backend/.env` y reiniciar la API |
| Login inválido / correo pendiente | Mismo proyecto en frontend/backend, usuario creado y correo confirmado |
| Error en salud protegida | Secreto JWT y token HS256 compatible |
| Tabla no encontrada / `PGRST205` | Migraciones pendientes en Supabase |
| Se requiere contexto de empresa | Completar Configuración → Empresa antes de cargar Excel |
| Falla la extensión Excel | Dependencias Python y acceso de DuckDB a descarga de extensiones |
| No se puede consultar Excel | Cube en puerto 4000, archivos generados disponibles y conexión aprobada |
| Codex no encontrado / sin sesión | `codex login status` y `CODEX_EXECUTABLE` |
| Timeout / modelo ausente en Ollama | Servicio activo, `ollama list`, modelo y URL correctos |
| Gemini devuelve 401/403/429 | Clave, acceso al modelo y cuota |
| Página existente devuelve 404 en desarrollo | Detener y volver a iniciar Next.js |

Validaciones disponibles:

```powershell
$env:PYTHONPATH = 'backend'
./backend/venv/Scripts/python.exe -m unittest discover -s backend/tests
npm --prefix frontend run build
```

Algunas evaluaciones adicionales requieren servicios, credenciales o datos. Ver [`backend/BI_HARNESS.md`](../backend/BI_HARNESS.md).

## Contenido de la entrega

Este repositorio contiene una copia limpia del codigo del TFG, con historial independiente. Las credenciales, el Excel, las bases locales, los CSV exportados, los modelos Cube generados, los logs y los archivos de trabajo se entregan por separado o se regeneran al importar el Excel. Solo se versionan plantillas `.env.example` sin valores privados.
