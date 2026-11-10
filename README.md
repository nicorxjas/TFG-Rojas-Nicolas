# BI AI - Trabajo Final de Grado

Aplicación de inteligencia de negocios conversacional. Permite consultar datos de un Excel mediante un chat y generar informes con inteligencia artificial.

## Guía de ejecución para el evaluador de la CAE

La evaluación utiliza **el proyecto Supabase existente**, con su base de datos y autenticación ya configuradas. No es necesario crear otro proyecto ni ejecutar migraciones.

### 1. Requisitos

Instalar en Windows:

- Node.js 20.9 o superior, con npm.
- Python 3.11 o superior.
- Docker Desktop.
- [Codex CLI](https://developers.openai.com/codex/cli), utilizado por la configuración actual para conectarse al LLM, con una cuenta que tenga acceso al modelo indicado en la configuración privada.

Se necesita conexión a Internet para acceder a Supabase y al LLM.

### 2. Preparar la configuración

Descargar este repositorio desde GitHub, descomprimirlo y abrir PowerShell en la carpeta principal. Tambien se puede clonar con Git:

```powershell
git clone https://github.com/nicorxjas/TFG-Rojas-Nicolas.git
cd TFG-Rojas-Nicolas
```

El autor debe facilitar por un canal privado los siguientes archivos, o las instrucciones y valores para crearlos:

| Archivo | Para qué sirve |
| --- | --- |
| `backend/.env` | Conexión al Supabase existente y configuración del LLM |
| `frontend/.env.local` | Conexión de la interfaz al mismo Supabase |
| `cube/.env` | Configuración del servicio que consulta el Excel |
| `data/Datos.xlsx` | Datos para realizar las pruebas |

Colocar cada archivo en la ubicación indicada. **Las credenciales se entregan por separado y no se publican en GitHub.** Si ya están presentes en el equipo, conservarlos.

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

El autor debe dejar habilitado el registro por correo y contraseña en el proyecto Supabase compartido y configurar `http://localhost:3000` como URL del sitio. La confirmación depende de la configuración de ese proyecto; ante un correo que no llega, contactar al autor.

### 6. Cargar el Excel

1. Abrir **[Configuración > Empresa](http://localhost:3000/settings/empresa)**, completar Empresa, Sector y Detalles y pulsar **Guardar cambios**. **Sector y Detalles son necesarios** para procesar el Excel.
2. Para los datos de ejemplo se puede usar: Empresa `Empresa Demo`, Sector `Comercio` y Detalles `Empresa que analiza ventas e inventario por cliente, producto y fecha. Busca conocer la evolución de las ventas y detectar oportunidades comerciales.`
3. Abrir **[Configuración > Conectores](http://localhost:3000/settings/conectores)** y seleccionar **Excel**.
4. Elegir el archivo `Datos.xlsx` facilitado por el autor y pulsar **Procesar workbook**. Puede estar en `data/Datos.xlsx` o en otra carpeta del equipo: se selecciona desde la interfaz.
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
