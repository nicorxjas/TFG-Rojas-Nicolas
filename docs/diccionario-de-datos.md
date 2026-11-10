# Diccionario de datos

Fuente: esquema DBML proporcionado. La columna **longitud** expresa el tamaño fijo de almacenamiento cuando PostgreSQL lo define; para `text`, `varchar`, `jsonb` y arreglos, el esquema no declara un límite máximo.

| Campo | longitud | tipo de datos | descripción |
|---|---:|---|---|
| `report_status` | 4 bytes | `enum` | Estado de generación de un informe. Valores: `PENDING`, `GENERATING`, `SUCCESS`, `FAILED`. |
| `semantic_metric_status` | 4 bytes | `enum` | Estado del ciclo de vida de una métrica semántica. Valores: `draft`, `active`, `archived`. |
| `users.id` | 16 bytes | `uuid` | Clave primaria. Identificador único del usuario. |
| `users.email` | No especificada | `text` | Obligatorio. Dirección de correo electrónico del usuario. |
| `users.full_name` | No especificada | `text` | Nombre completo del usuario. |
| `users.created_at` | 8 bytes | `timestamptz` | Fecha y hora de creación del usuario, con zona horaria. |
| `profiles.id` | 16 bytes | `uuid` | Clave primaria y foránea a `users.id`; establece la relación uno a uno con el usuario. |
| `profiles.email` | No especificada | `text` | Correo electrónico mostrado en el perfil. |
| `profiles.full_name` | No especificada | `text` | Nombre completo mostrado en el perfil. |
| `profiles.title` | No especificada | `text` | Cargo o título profesional del usuario. |
| `profiles.username` | No especificada | `text` | Nombre de usuario público o identificador legible. |
| `profiles.avatar_url` | No especificada | `text` | URL de la imagen de perfil. |
| `profiles.created_at` | 8 bytes | `timestamptz` | Fecha y hora de creación del perfil. |
| `profiles.updated_at` | 8 bytes | `timestamptz` | Fecha y hora de la última actualización del perfil. |
| `company_settings.id` | 16 bytes | `uuid` | Clave primaria y foránea a `users.id`; identifica la configuración empresarial de cada usuario. |
| `company_settings.company_name` | No especificada | `text` | Nombre de la empresa configurada por el usuario. |
| `company_settings.sector` | No especificada | `text` | Sector o industria de la empresa. |
| `company_settings.details` | No especificada | `text` | Información adicional o contexto descriptivo de la empresa. |
| `company_settings.created_at` | 8 bytes | `timestamptz` | Fecha y hora de creación de la configuración. |
| `company_settings.updated_at` | 8 bytes | `timestamptz` | Fecha y hora de la última actualización de la configuración. |
| `connectors.id` | 16 bytes | `uuid` | Clave primaria. Identificador único del conector disponible. |
| `connectors.key` | No especificada | `text` | Obligatorio y único. Clave técnica estable del conector. |
| `connectors.name` | No especificada | `text` | Obligatorio. Nombre visible del conector. |
| `connectors.description` | No especificada | `text` | Obligatorio. Descripción funcional del conector. |
| `connectors.logo_path` | No especificada | `text` | Ruta o URL del logotipo del conector. |
| `connectors.section` | No especificada | `text` | Obligatorio. Sección de la interfaz o categoría donde se presenta el conector. |
| `connectors.status` | No especificada | `text` | Obligatorio. Estado de disponibilidad del conector. |
| `connectors.sort_order` | 4 bytes | `int4` | Obligatorio. Orden de presentación del conector. |
| `connectors.created_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de creación del registro. |
| `connectors.updated_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de la última actualización. |
| `connector_instances.id` | 16 bytes | `uuid` | Clave primaria. Identificador único de la instancia de conexión. |
| `connector_instances.owner_user_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `users.id`; usuario propietario de la conexión. |
| `connector_instances.connector_key` | No especificada | `text` | Obligatorio. Clave foránea a `connectors.key`; tipo de conector utilizado. |
| `connector_instances.provider` | No especificada | `text` | Obligatorio. Proveedor externo de la conexión. |
| `connector_instances.name` | No especificada | `text` | Obligatorio. Nombre asignado a la instancia. |
| `connector_instances.auth_mode` | No especificada | `text` | Obligatorio. Modalidad de autenticación utilizada. |
| `connector_instances.status` | No especificada | `text` | Obligatorio. Estado operativo de la conexión. |
| `connector_instances.is_default` | 1 byte | `bool` | Obligatorio. Indica si es la conexión predeterminada del usuario. |
| `connector_instances.config` | Variable | `jsonb` | Obligatorio. Configuración no secreta de la conexión. |
| `connector_instances.health` | Variable | `jsonb` | Obligatorio. Información estructurada sobre la salud de la conexión. |
| `connector_instances.last_sync_at` | 8 bytes | `timestamptz` | Fecha y hora de la última sincronización. |
| `connector_instances.last_error` | No especificada | `text` | Detalle del último error registrado. |
| `connector_instances.created_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de creación de la instancia. |
| `connector_instances.updated_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de la última actualización. |
| `connector_secrets.connection_id` | 16 bytes | `uuid` | Clave primaria y foránea a `connector_instances.id`; conexión a la que pertenecen los secretos. |
| `connector_secrets.owner_user_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `users.id`; propietario de los secretos. |
| `connector_secrets.secret_payload` | Variable | `jsonb` | Obligatorio. Contenedor estructurado del material secreto de la conexión. |
| `connector_secrets.secret_version` | 4 bytes | `int4` | Obligatorio. Versión del formato o contenido secreto. |
| `connector_secrets.created_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de creación del secreto. |
| `connector_secrets.updated_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de la última actualización del secreto. |
| `connector_app_configs.id` | 16 bytes | `uuid` | Clave primaria. Identificador único de la configuración de aplicación. |
| `connector_app_configs.owner_user_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `users.id`; usuario propietario de la configuración. |
| `connector_app_configs.connector_key` | No especificada | `text` | Obligatorio. Clave técnica del conector configurado. |
| `connector_app_configs.provider` | No especificada | `text` | Obligatorio. Proveedor de la aplicación externa. |
| `connector_app_configs.tenant_id` | No especificada | `text` | Obligatorio. Identificador del tenant en el proveedor. |
| `connector_app_configs.client_id` | No especificada | `text` | Obligatorio. Identificador público del cliente OAuth o de la aplicación. |
| `connector_app_configs.redirect_uri` | No especificada | `text` | Obligatorio. URI de redirección configurada para la autenticación. |
| `connector_app_configs.scopes` | Variable | `text[]` | Obligatorio. Lista de permisos solicitados al proveedor. |
| `connector_app_configs.secret_configured` | 1 byte | `bool` | Obligatorio. Indica si el secreto de la aplicación ya fue configurado. |
| `connector_app_configs.metadata` | Variable | `jsonb` | Obligatorio. Metadatos adicionales de la configuración. |
| `connector_app_configs.created_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de creación. |
| `connector_app_configs.updated_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de la última actualización. |
| `connector_app_secrets.owner_user_id` | 16 bytes | `uuid` | Parte de la clave primaria compuesta y clave foránea a `users.id`; propietario del secreto. |
| `connector_app_secrets.connector_key` | No especificada | `text` | Parte de la clave primaria compuesta; clave técnica del conector. |
| `connector_app_secrets.secret_payload` | Variable | `jsonb` | Obligatorio. Contenedor estructurado del secreto de aplicación. |
| `connector_app_secrets.secret_version` | 4 bytes | `int4` | Obligatorio. Versión del secreto o de su formato. |
| `connector_app_secrets.created_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de creación del secreto. |
| `connector_app_secrets.updated_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de la última actualización del secreto. |
| `semantic_models.id` | 16 bytes | `uuid` | Clave primaria. Identificador único del modelo semántico. |
| `semantic_models.owner_user_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `users.id`; propietario del modelo. |
| `semantic_models.connection_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `connector_instances.id`; conexión de origen. |
| `semantic_models.provider` | No especificada | `text` | Obligatorio. Proveedor del modelo semántico. |
| `semantic_models.external_model_id` | No especificada | `text` | Obligatorio. Identificador del modelo en el sistema externo. |
| `semantic_models.workspace_id` | No especificada | `text` | Identificador del espacio de trabajo externo. |
| `semantic_models.dataset_id` | No especificada | `text` | Identificador del conjunto de datos externo. |
| `semantic_models.name` | No especificada | `text` | Obligatorio. Nombre del modelo semántico. |
| `semantic_models.description` | No especificada | `text` | Obligatorio. Descripción del propósito y alcance del modelo. |
| `semantic_models.is_default` | 1 byte | `bool` | Obligatorio. Indica si es el modelo predeterminado del usuario o conexión. |
| `semantic_models.metadata` | Variable | `jsonb` | Obligatorio. Metadatos adicionales obtenidos del proveedor. |
| `semantic_models.created_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de creación. |
| `semantic_models.updated_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de la última actualización. |
| `semantic_tables.id` | 16 bytes | `uuid` | Clave primaria. Identificador único de la tabla semántica. |
| `semantic_tables.owner_user_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `users.id`; propietario del registro. |
| `semantic_tables.model_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `semantic_models.id`; modelo al que pertenece la tabla. |
| `semantic_tables.external_table_id` | No especificada | `text` | Identificador de la tabla en el sistema externo. |
| `semantic_tables.name` | No especificada | `text` | Obligatorio. Nombre técnico de la tabla. |
| `semantic_tables.display_name` | No especificada | `text` | Obligatorio. Nombre de presentación de la tabla. |
| `semantic_tables.description` | No especificada | `text` | Obligatorio. Descripción técnica o funcional de la tabla. |
| `semantic_tables.is_hidden` | 1 byte | `bool` | Obligatorio. Indica si la tabla está oculta para consumo. |
| `semantic_tables.metadata` | Variable | `jsonb` | Obligatorio. Metadatos adicionales de la tabla. |
| `semantic_tables.created_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de creación. |
| `semantic_tables.updated_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de la última actualización. |
| `semantic_tables.business_name` | No especificada | `text` | Obligatorio. Nombre de negocio aprobado para la tabla. |
| `semantic_tables.suggested_business_name` | No especificada | `text` | Nombre de negocio sugerido, por ejemplo por un proceso automático. |
| `semantic_tables.suggested_description` | No especificada | `text` | Descripción de negocio sugerida. |
| `semantic_tables.approval_status` | No especificada | `text` | Obligatorio. Estado del proceso de revisión o aprobación. |
| `semantic_tables.approved_at` | 8 bytes | `timestamptz` | Fecha y hora de aprobación. |
| `semantic_tables.approved_by` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `users.id`; usuario que aprobó el registro. |
| `semantic_fields.id` | 16 bytes | `uuid` | Clave primaria. Identificador único del campo semántico. |
| `semantic_fields.owner_user_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `users.id`; propietario del registro. |
| `semantic_fields.model_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `semantic_models.id`; modelo al que pertenece el campo. |
| `semantic_fields.table_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `semantic_tables.id`; tabla a la que pertenece el campo. |
| `semantic_fields.external_field_id` | No especificada | `text` | Identificador del campo en el sistema externo. |
| `semantic_fields.semantic_key` | No especificada | `text` | Obligatorio. Clave semántica estable del campo. |
| `semantic_fields.name` | No especificada | `text` | Obligatorio. Nombre técnico del campo. |
| `semantic_fields.display_name` | No especificada | `text` | Obligatorio. Nombre de presentación del campo. |
| `semantic_fields.description` | No especificada | `text` | Obligatorio. Descripción técnica o funcional del campo. |
| `semantic_fields.field_kind` | No especificada | `text` | Obligatorio. Clase semántica del campo, como dimensión, medida o atributo. |
| `semantic_fields.data_type` | No especificada | `text` | Tipo de datos reportado por el origen o la capa semántica. |
| `semantic_fields.expression` | No especificada | `text` | Expresión de cálculo asociada al campo. |
| `semantic_fields.expression_language` | No especificada | `text` | Lenguaje en el que está escrita la expresión. |
| `semantic_fields.format_string` | No especificada | `text` | Cadena de formato para presentar el valor. |
| `semantic_fields.is_hidden` | 1 byte | `bool` | Obligatorio. Indica si el campo está oculto para consumo. |
| `semantic_fields.is_sensitive` | 1 byte | `bool` | Obligatorio. Indica si el campo contiene información sensible. |
| `semantic_fields.is_ai_enabled` | 1 byte | `bool` | Obligatorio. Indica si el campo puede utilizarse en funciones de IA. |
| `semantic_fields.metadata` | Variable | `jsonb` | Obligatorio. Metadatos adicionales del campo. |
| `semantic_fields.created_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de creación. |
| `semantic_fields.updated_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de la última actualización. |
| `semantic_fields.business_name` | No especificada | `text` | Obligatorio. Nombre de negocio aprobado para el campo. |
| `semantic_fields.suggested_business_name` | No especificada | `text` | Nombre de negocio sugerido para el campo. |
| `semantic_fields.suggested_description` | No especificada | `text` | Descripción de negocio sugerida para el campo. |
| `semantic_fields.approval_status` | No especificada | `text` | Obligatorio. Estado del proceso de revisión o aprobación. |
| `semantic_fields.approved_at` | 8 bytes | `timestamptz` | Fecha y hora de aprobación. |
| `semantic_fields.approved_by` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `users.id`; usuario que aprobó el campo. |
| `semantic_relationships.id` | 16 bytes | `uuid` | Clave primaria. Identificador único de la relación semántica. |
| `semantic_relationships.owner_user_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `users.id`; propietario de la relación. |
| `semantic_relationships.model_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `semantic_models.id`; modelo que contiene la relación. |
| `semantic_relationships.from_table` | No especificada | `text` | Obligatorio. Tabla de origen de la relación. |
| `semantic_relationships.from_field` | No especificada | `text` | Obligatorio. Campo de origen de la relación. |
| `semantic_relationships.to_table` | No especificada | `text` | Obligatorio. Tabla de destino de la relación. |
| `semantic_relationships.to_field` | No especificada | `text` | Obligatorio. Campo de destino de la relación. |
| `semantic_relationships.cardinality` | No especificada | `text` | Cardinalidad de la relación, por ejemplo uno a muchos. |
| `semantic_relationships.cross_filter_behavior` | No especificada | `text` | Comportamiento de propagación de filtros entre tablas. |
| `semantic_relationships.is_active` | 1 byte | `bool` | Obligatorio. Indica si la relación está activa. |
| `semantic_relationships.metadata` | Variable | `jsonb` | Obligatorio. Metadatos adicionales de la relación. |
| `semantic_relationships.created_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de creación. |
| `semantic_relationships.updated_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de la última actualización. |
| `semantic_sync_runs.id` | 16 bytes | `uuid` | Clave primaria. Identificador único de la ejecución de sincronización. |
| `semantic_sync_runs.owner_user_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `users.id`; usuario que posee la ejecución. |
| `semantic_sync_runs.connection_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `connector_instances.id`; conexión sincronizada. |
| `semantic_sync_runs.status` | No especificada | `text` | Obligatorio. Estado de la ejecución de sincronización. |
| `semantic_sync_runs.scan_id` | No especificada | `text` | Identificador del escaneo en el proveedor externo. |
| `semantic_sync_runs.started_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de inicio de la ejecución. |
| `semantic_sync_runs.completed_at` | 8 bytes | `timestamptz` | Fecha y hora de finalización de la ejecución. |
| `semantic_sync_runs.error_message` | No especificada | `text` | Mensaje de error producido por la sincronización. |
| `semantic_sync_runs.counters` | Variable | `jsonb` | Obligatorio. Contadores de elementos procesados, creados o actualizados. |
| `semantic_sync_runs.metadata` | Variable | `jsonb` | Obligatorio. Metadatos adicionales de la ejecución. |
| `semantic_aliases.id` | 16 bytes | `uuid` | Clave primaria. Identificador único del alias. |
| `semantic_aliases.owner_user_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `users.id`; propietario del alias. |
| `semantic_aliases.model_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `semantic_models.id`; modelo al que pertenece el alias. |
| `semantic_aliases.semantic_key` | No especificada | `text` | Obligatorio. Clave semántica de la entidad referenciada. |
| `semantic_aliases.entity_type` | No especificada | `text` | Obligatorio. Tipo de entidad a la que se aplica el alias. |
| `semantic_aliases.alias` | No especificada | `text` | Obligatorio. Variante de nombre reconocida para la entidad. |
| `semantic_aliases.normalized_alias` | No especificada | `text` | Obligatorio. Alias normalizado para comparación y búsqueda. |
| `semantic_aliases.created_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de creación. |
| `semantic_aliases.updated_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de la última actualización. |
| `semantic_metrics.id` | 16 bytes | `uuid` | Clave primaria. Identificador único de la métrica semántica. |
| `semantic_metrics.user_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `users.id`; usuario propietario o creador de la métrica. |
| `semantic_metrics.name` | No especificada | `varchar` | Obligatorio. Nombre visible de la métrica. |
| `semantic_metrics.slug` | No especificada | `varchar` | Obligatorio. Identificador legible utilizado en URLs o referencias. |
| `semantic_metrics.metric_key` | No especificada | `varchar` | Obligatorio. Clave técnica estable de la métrica. |
| `semantic_metrics.description` | No especificada | `text` | Descripción funcional de la métrica. |
| `semantic_metrics.expression` | No especificada | `text` | Obligatorio. Expresión fuente que define el cálculo. |
| `semantic_metrics.compiled_expression` | No especificada | `text` | Obligatorio. Expresión compilada o normalizada lista para ejecución. |
| `semantic_metrics.variables` | Variable | `jsonb` | Obligatorio. Variables o parámetros estructurados de la métrica. |
| `semantic_metrics.dependencies` | Variable | `text[]` | Obligatorio. Dependencias lógicas de la métrica. |
| `semantic_metrics.cube_dependencies` | Variable | `text[]` | Obligatorio. Dependencias específicas de modelos o cubos analíticos. |
| `semantic_metrics.format` | No especificada | `varchar` | Obligatorio. Formato de presentación del resultado. |
| `semantic_metrics.status` | 4 bytes | `semantic_metric_status` | Obligatorio. Estado de la métrica: `draft`, `active` o `archived`. |
| `semantic_metrics.created_by_ai` | 1 byte | `bool` | Obligatorio. Indica si la métrica fue generada por IA. |
| `semantic_metrics.approved_at` | 8 bytes | `timestamptz` | Fecha y hora de aprobación de la métrica. |
| `semantic_metrics.created_at` | 8 bytes | `timestamptz` | Fecha y hora de creación. |
| `semantic_metrics.updated_at` | 8 bytes | `timestamptz` | Fecha y hora de la última actualización. |
| `semantic_metric_drafts.id` | 16 bytes | `uuid` | Clave primaria. Identificador único del borrador de métrica. |
| `semantic_metric_drafts.owner_user_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `users.id`; propietario del borrador. |
| `semantic_metric_drafts.connection_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `connector_instances.id`; conexión utilizada como contexto. |
| `semantic_metric_drafts.name` | No especificada | `text` | Obligatorio. Nombre propuesto para la métrica. |
| `semantic_metric_drafts.description` | No especificada | `text` | Obligatorio. Descripción propuesta para la métrica. |
| `semantic_metric_drafts.expression` | Variable | `jsonb` | Obligatorio. Definición estructurada de la expresión de cálculo. |
| `semantic_metric_drafts.compiled_payload` | Variable | `jsonb` | Obligatorio. Resultado estructurado de la compilación del borrador. |
| `semantic_metric_drafts.dependencies` | Variable | `text[]` | Obligatorio. Lista de dependencias del borrador. |
| `semantic_metric_drafts.status` | No especificada | `text` | Obligatorio. Estado del flujo de elaboración del borrador. |
| `semantic_metric_drafts.created_by_ai` | 1 byte | `bool` | Obligatorio. Indica si el borrador fue generado por IA. |
| `semantic_metric_drafts.source_prompt` | No especificada | `text` | Obligatorio. Instrucción de origen utilizada para generar el borrador. |
| `semantic_metric_drafts.created_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de creación. |
| `semantic_metric_drafts.updated_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de la última actualización. |
| `categories.id` | 16 bytes | `uuid` | Clave primaria. Identificador único de la categoría. |
| `categories.name` | No especificada | `text` | Obligatorio. Nombre visible de la categoría. |
| `categories.slug` | No especificada | `text` | Obligatorio y único. Clave legible utilizada para referenciar la categoría. |
| `categories.icon_type` | No especificada | `text` | Obligatorio. Tipo o biblioteca del icono. |
| `categories.icon_name` | No especificada | `text` | Obligatorio. Nombre técnico del icono. |
| `categories.icon_color` | No especificada | `text` | Obligatorio. Color asociado al icono. |
| `categories.icon_emoji` | No especificada | `text` | Emoji alternativo o complementario del icono. |
| `categories.created_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de creación. |
| `categories.updated_at` | 8 bytes | `timestamptz` | Obligatorio. Fecha y hora de la última actualización. |
| `agents.id` | 16 bytes | `uuid` | Clave primaria. Identificador único del agente. |
| `agents.name` | No especificada | `varchar` | Obligatorio. Nombre visible del agente. |
| `agents.description` | No especificada | `text` | Descripción del propósito o especialidad del agente. |
| `agents.system_prompt` | No especificada | `text` | Obligatorio. Instrucción de sistema que define el comportamiento del agente. |
| `agents.category` | No especificada | `text` | Obligatorio. Clave foránea a `categories.slug`; categoría del agente. |
| `agents.created_at` | 8 bytes | `timestamptz` | Fecha y hora de creación del agente. |
| `agents.icon_type` | No especificada | `varchar` | Tipo o biblioteca del icono del agente. |
| `agents.icon_name` | No especificada | `varchar` | Nombre técnico del icono del agente. |
| `agents.icon_color` | No especificada | `varchar` | Color asociado al icono del agente. |
| `agents.icon_emoji` | No especificada | `text` | Emoji alternativo o complementario del agente. |
| `skills.id` | 16 bytes | `uuid` | Clave primaria. Identificador único de la habilidad. |
| `skills.name` | No especificada | `varchar` | Obligatorio. Nombre visible de la habilidad. |
| `skills.description` | No especificada | `text` | Descripción del propósito de la habilidad. |
| `skills.instruction` | No especificada | `text` | Obligatorio. Instrucción o contenido operativo de la habilidad. |
| `skills.created_at` | 8 bytes | `timestamptz` | Fecha y hora de creación de la habilidad. |
| `skills.updated_at` | 8 bytes | `timestamptz` | Fecha y hora de la última actualización. |
| `skill_agents.skill_id` | 16 bytes | `uuid` | Parte de la clave primaria compuesta y clave foránea a `skills.id`. |
| `skill_agents.agent_id` | 16 bytes | `uuid` | Parte de la clave primaria compuesta y clave foránea a `agents.id`. |
| `skill_agents.created_at` | 8 bytes | `timestamptz` | Fecha y hora en que la habilidad fue asociada al agente. |
| `reports.id` | 16 bytes | `uuid` | Clave primaria. Identificador único del informe. |
| `reports.user_id` | 16 bytes | `uuid` | Obligatorio. Clave foránea a `users.id`; usuario propietario del informe. |
| `reports.status` | 4 bytes | `report_status` | Obligatorio. Estado de generación: `PENDING`, `GENERATING`, `SUCCESS` o `FAILED`. |
| `reports.content` | Variable | `jsonb` | Contenido estructurado generado para el informe. |
| `reports.error_log` | No especificada | `text` | Detalle del error ocurrido durante la generación. |
| `reports.created_at` | 8 bytes | `timestamptz` | Fecha y hora de creación del informe. |
| `reports.updated_at` | 8 bytes | `timestamptz` | Fecha y hora de la última actualización. |
| `reports.name` | No especificada | `varchar` | Nombre del informe. |
| `reports.prompt` | No especificada | `text` | Instrucción utilizada para generar el informe. |
| `reports.include_charts` | 1 byte | `bool` | Indica si el informe debe incluir gráficos. |
| `report_agents.report_id` | 16 bytes | `uuid` | Parte de la clave primaria compuesta y clave foránea a `reports.id`. |
| `report_agents.agent_id` | 16 bytes | `uuid` | Parte de la clave primaria compuesta y clave foránea a `agents.id`. |

## Criterios de longitud

- `uuid`: 16 bytes.
- `timestamptz`: 8 bytes.
- `int4`: 4 bytes.
- `bool`: 1 byte.
- Tipos `enum`: 4 bytes de almacenamiento interno en PostgreSQL.
- `text` y `varchar` sin parámetro: longitud máxima no especificada por el esquema.
- `jsonb` y arreglos: longitud variable según el contenido.
