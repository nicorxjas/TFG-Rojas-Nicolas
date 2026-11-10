# BI AI - Trabajo Final de Grado

Aplicación de inteligencia de negocios conversacional. Permite consultar datos de un Excel mediante un chat y generar informes con inteligencia artificial.

## Guía de ejecución para el evaluador de la CAE

La evaluación utiliza **el proyecto Supabase existente**, con su base de datos y autenticación ya configuradas. No es necesario crear otro proyecto ni ejecutar migraciones.

### 1. Requisitos

Instalar en Windows:

- Node.js 20.9 o superior, con npm.
- Python 3.11 o superior.
- Docker Desktop.
- [Codex CLI](https://developers.openai.com/codex/cli), utilizado por la configuración actual para conectarse al LLM, con una cuenta que tenga acceso al modelo `gpt-5.6-luna` indicado abajo.

Se necesita conexión a Internet para acceder a Supabase y al LLM.

### 2. Preparar la configuración

Descargar este repositorio desde GitHub, descomprimirlo y abrir PowerShell en la carpeta principal. Tambien se puede clonar con Git:

```powershell
git clone https://github.com/nicorxjas/TFG-Rojas-Nicolas.git
cd TFG-Rojas-Nicolas
```

Crear estos tres archivos de configuración. Se pueden copiar las plantillas **solo si todavía no existen los archivos de destino**, para conservar cualquier configuración local:

```powershell
if (!(Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
if (!(Test-Path frontend/.env.local)) { Copy-Item frontend/.env.example frontend/.env.local }
if (!(Test-Path cube/.env)) { Copy-Item cube/.env.example cube/.env }
```

Después, completar los tres archivos con los bloques de abajo. Esta demo utiliza **Excel como fuente de datos**, el proyecto Supabase ya configurado y **Codex con `gpt-5.6-luna`**. Este README reúne los valores necesarios para preparar el entorno de evaluación.

#### Backend: `backend/.env`

```dotenv
SUPABASE_URL=https://nfcbzgykivueumciocuy.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5mY2J6Z3lraXZ1ZXVtY2lvY3V5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTU2MTUyOSwiZXhwIjoyMDkxMTM3NTI5fQ.Cc1rQ2kYNRtQRkHZLM8ELZ6dzerdKjMXqF_2haZQLFA
SUPABASE_JWT_SECRET=e6f09e5d-ace3-4304-903c-9b5b39942888

LLM_PROVIDER=codex
LLM_MODEL=gpt-5.6-luna
CODEX_REASONING_EFFORT=low
CODEX_TIMEOUT_SECONDS=120
CODEX_EXECUTABLE=

CUBE_API_URL=http://localhost:4000/cubejs-api/v1/load
CUBEJS_API_SECRET=

REPORT_LLM_MODEL=
REPORT_LLM_TIMEOUT_SECONDS=
REPORT_LLM_MAX_TOKENS=
REPORT_LLM_MAX_RETRIES=5
SEMANTIC_CATALOG_CACHE_TTL_SECONDS=30
BI_TRACE_DIR=backend/runtime/bi-traces
DATABASE_URL=
```

#### Interfaz: `frontend/.env.local`

```dotenv
NEXT_PUBLIC_SUPABASE_URL=https://nfcbzgykivueumciocuy.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=sb_publishable_AkTnNLkr7K0JsM1JQTWImA_IiWjHXS_
NEXT_PUBLIC_API_URL=http://localhost:8000
```

`NEXT_PUBLIC_SUPABASE_ANON_KEY` contiene la clave pública de Supabase. La clave `SUPABASE_SERVICE_ROLE_KEY` se utiliza únicamente en el backend.

#### Servicio Excel: `cube/.env`

```dotenv
CUBEJS_DB_TYPE=duckdb
CUBEJS_DB_NAME=/data/nyro_analytics.db
CUBEJS_DB_DUCKDB_DATABASE_PATH=/data/nyro_analytics.db
CUBEJS_DEV_MODE=true
CUBEJS_API_SECRET=nyro_super_secret_token_2026
```

Copiar cada bloque completo al archivo indicado. Los campos vacíos se dejan vacíos: los informes heredan el modelo general y sus límites del código, y `DATABASE_URL` solo se utiliza en scripts auxiliares de mantenimiento. `CODEX_EXECUTABLE` solo se completa con la ruta a `codex.exe` si no se detecta automáticamente.

En `backend/.env`, `CUBEJS_API_SECRET` queda vacío porque el servicio Cube se ejecuta localmente en modo de desarrollo (`CUBEJS_DEV_MODE=true`). El valor incluido en `cube/.env` es el secreto de firma del servicio, no un token JWT para el backend.

El archivo `.env` de la raíz no se utiliza. Guardar cada archivo en su ruta, con un solo valor por variable y sin comentarios al final de las líneas. Reiniciar backend, frontend o Cube después de modificar su configuración. Los archivos `.env` locales están excluidos de Git.

Para la conexión al LLM, iniciar sesión en Codex CLI con una cuenta que tenga acceso al modelo configurado. Esta sesión es independiente de la cuenta que se creará dentro de BI AI:

```powershell
codex login
codex login status
```

La aplicación utiliza automáticamente el proveedor y el modelo definidos en `backend/.env`. Las credenciales de Codex las administra el CLI; no se copian al repositorio. Si `codex` no se reconoce, seguir la instalación oficial y volver a abrir PowerShell. Si se utiliza el ejecutable incluido en Codex Desktop, indicar su ruta en `CODEX_EXECUTABLE` y usar esa misma ruta para iniciar sesión.

### 3. Instalar dependencias

Ejecutar una sola vez desde la carpeta principal:

```powershell
python -m venv backend/venv
./backend/venv/Scripts/python.exe -m pip install -r backend/requirements.txt
npm --prefix frontend ci
```

### 4. Iniciar la aplicación

Abrir Docker Desktop y ejecutar:

```powershell
docker compose -f cube/docker-compose.yml up -d
```

En una terminal PowerShell, iniciar el backend:

```powershell
./backend/venv/Scripts/python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

En otra terminal PowerShell, iniciar la interfaz:

```powershell
npm --prefix frontend run dev
```

Mantener ambas terminales abiertas. Si el puerto 3000 está ocupado, liberarlo antes de continuar para conservar las direcciones de esta guía.

### 5. Crear una cuenta

1. Abrir **[http://localhost:3000/signup](http://localhost:3000/signup)**.
2. Ingresar un correo al que se tenga acceso y una contraseña de **al menos 8 caracteres, con un número y un símbolo**.
3. Pulsar **Create account**. Para esta demo, utilizar el formulario de correo y contraseña.
4. Si Supabase solicita confirmación, abrir el correo recibido y confirmar la cuenta; revisar también la carpeta de spam.
5. Abrir **[http://localhost:3000/login](http://localhost:3000/login)** e ingresar con las credenciales elegidas. El registro actual no redirige automáticamente ni muestra un aviso de éxito en pantalla.

Ante un correo que no llega, contactar al autor.

### 6. Cargar el Excel

1. Abrir **[Configuración > Empresa](http://localhost:3000/settings/empresa)**, completar Empresa, Sector y Detalles y pulsar **Guardar cambios**. **Sector y Detalles son necesarios** para procesar el Excel.
2. Para los datos de ejemplo se puede usar: Empresa `Empresa Demo`, Sector `Comercio` y Detalles `Empresa que analiza ventas e inventario por cliente, producto y fecha. Busca conocer la evolución de las ventas y detectar oportunidades comerciales.`
3. Abrir **[Configuración > Conectores](http://localhost:3000/settings/conectores)** y seleccionar **Excel**.
4. Elegir el archivo `Datos.xlsx` facilitado por el autor y pulsar **Procesar workbook**. 
5. Esperar a que termine el procesamiento y se abra **Onboarding semántico**.
6. Revisar los campos detectados y pulsar **Aprobar conceptos** si son correctos.
7. Revisar los indicadores base y pulsar **Aprobar** en cada uno de los pendientes. Si se generan sugerencias adicionales, aprobar o rechazar cada sugerencia según corresponda.
8. Pulsar **Completar** y comprobar que aparezca **Modelo listo**. Cerrar el asistente para continuar.

El archivo debe ser `.xlsx` y pesar menos de 25 MB. El sistema prepara automáticamente los archivos necesarios para consultar sus datos.

**Cada cuenta nueva debe cargar y aprobar su propia conexión.** Colocar el Excel en la carpeta `data/` no lo importa automáticamente. La primera carga puede necesitar Internet para descargar la extensión de Excel de DuckDB.

### 7. Probar el sistema

1. Abrir el chat y consultar: **«¿Cuál es el total de ventas del último año con datos?»**.
2. Continuar con: **«¿Cuáles son los cinco productos con mayores ventas en ese período?»**.
3. Abrir **Informes**, crear un informe y solicitar: **«Prepará un resumen de las ventas del último año con datos, con los principales resultados y oportunidades de mejora»**.

Usar períodos presentes en el Excel: las fechas del archivo de demostración pueden no coincidir con la semana o el mes actual.

### Detener la aplicación

Presionar `Ctrl+C` en las terminales del backend y de la interfaz. Para detener el servicio de Docker:

```powershell
docker compose -f cube/docker-compose.yml down
```

Si hay un error de conexión, comprobar que Docker Desktop esté abierto, que ambas terminales sigan ejecutándose y que los archivos de configuración estén en las ubicaciones indicadas.

La configuración avanzada y las indicaciones de mantenimiento están en la [guía técnica](docs/guia-tecnica.md).
