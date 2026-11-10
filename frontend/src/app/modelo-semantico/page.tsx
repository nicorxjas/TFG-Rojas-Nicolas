"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import {
  AlertCircle,
  Calculator,
  ChevronDown,
  Check,
  CircleDollarSign,
  Clock3,
  Hash,
  ListFilter,
  Network,
  Pencil,
  Plus,
  Search,
  Save,
  ShieldCheck,
  Sparkles,
  Text,
  Trash2,
  WandSparkles,
  X,
} from "lucide-react";
import { getSupabaseAuthHeaders } from "@/lib/supabase/auth";

type FieldType = "texto" | "numero" | "fecha";
type ViewMode = "fields" | "metrics";
type MetricAggregation = "sum" | "count" | "countDistinct" | "number";

type SemanticField = {
  id?: string;
  key: string;
  name: string;
  description: string;
  type: FieldType;
};

type SemanticMetric = {
  id?: string;
  fieldId?: string;
  modelId?: string;
  key: string;
  name: string;
  description: string;
  definition?: string;
  aggregation: MetricAggregation;
  format?: string;
  formula?: string;
  source?: "cube" | "custom" | "powerbi" | "excel";
};

type SemanticArea = {
  id: string;
  modelId?: string;
  source?: string;
  name: string;
  businessName: string;
  summary: string;
  icon: LucideIcon;
  tone: string;
  fields: SemanticField[];
  metrics: SemanticMetric[];
};

type ValidationResult =
  | { valid: true; dependencies: string[]; cube_dependencies: string[] }
  | { valid: false; error: string };

type CatalogConnection = {
  id: string;
  connector_key?: string;
  name: string;
  provider: string;
  status: string;
  is_default: boolean;
  config?: {
    workspace_name?: string;
    dataset_name?: string;
    file_name?: string;
  };
  last_sync_at?: string | null;
  last_error?: string | null;
};

type CatalogTable = {
  id: string;
  model_id: string;
  name: string;
  display_name?: string;
  business_name?: string;
  suggested_business_name?: string;
  suggested_description?: string;
  approval_status?: "review" | "approved" | "rejected";
  description?: string;
  metadata?: {
    source?: string;
    provider?: string;
    row_count?: number;
    sheet_name?: string;
    table_name?: string;
  };
};

type CatalogField = {
  id: string;
  model_id?: string;
  semantic_key: string;
  name: string;
  display_name?: string;
  business_name?: string;
  suggested_business_name?: string;
  suggested_description?: string;
  approval_status?: "review" | "approved" | "rejected";
  description?: string;
  field_kind: "measure" | "dimension" | "time" | "id" | "unknown";
  data_type?: string;
  format_string?: string;
  expression?: string;
  source?: string;
  is_hidden?: boolean;
  is_ai_enabled?: boolean;
  metadata?: Record<string, unknown>;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const fieldIcon = {
  texto: Text,
  numero: Hash,
  fecha: Clock3,
};

const aggregationLabel: Record<MetricAggregation, string> = {
  sum: "Suma",
  count: "Conteo",
  countDistinct: "Unicos",
  number: "Definicion",
};

function hasTechnicalText(value?: string) {
  const text = String(value || "");
  return (
    /\b(?:sum|count|avg|min|max|countDistinct|count_distinct)\s*\(/i.test(text) ||
    /\bExcel[a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)?/i.test(text) ||
    /\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\b/.test(text) ||
    /\b(?:formula|sql|cube|backend|llm)\b/i.test(text)
  );
}

function businessText(value: unknown, fallback: string) {
  if (typeof value !== "string" && typeof value !== "number") return fallback;
  const text = String(value || "").replaceAll("@", "").trim();
  if (!text || hasTechnicalText(text)) return fallback;
  return text;
}

function sourceDisplayName(source?: string) {
  if (source === "excel") return "Datos cargados";
  if (source === "powerbi") return "Modelo conectado";
  if (source === "cube") return "Modelo semantico";
  if (source === "custom") return "Indicador creado";
  return "Fuente conectada";
}

const metricTemplates = [
  "Quiero calcular la cantidad de productos existentes",
  "Quiero calcular la cantidad existente de proveedores",
  "Quiero contar clientes existentes",
  "Quiero calcular el margen bruto",
  "Quiero un porcentaje de margen",
];

const activeConnectionStorageKey = "nyro_active_connection_id";

function readStoredActiveConnectionId() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(activeConnectionStorageKey) || "";
}

function writeStoredActiveConnectionId(connectionId: string) {
  if (typeof window === "undefined") return;
  if (connectionId) {
    window.localStorage.setItem(activeConnectionStorageKey, connectionId);
  } else {
    window.localStorage.removeItem(activeConnectionStorageKey);
  }
}

function CatalogLoadingSkeleton() {
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[330px_minmax(0,1fr)]" aria-busy="true">
      <section className="self-start overflow-hidden rounded-xl border border-zinc-800/80 bg-zinc-900/20">
        <div className="flex items-center justify-between border-b border-zinc-800/70 px-4 py-3">
          <div className="h-3 w-32 animate-pulse rounded bg-zinc-800" />
          <div className="h-3 w-5 animate-pulse rounded bg-zinc-800" />
        </div>
        <div className="space-y-2 p-2">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="rounded-lg border border-transparent px-3 py-3">
              <div className="flex items-start gap-3">
                <div className="h-8 w-8 shrink-0 animate-pulse rounded-lg bg-zinc-800" />
                <div className="min-w-0 flex-1 space-y-2">
                  <div className="h-3 w-36 animate-pulse rounded bg-zinc-800" />
                  <div className="h-2.5 w-24 animate-pulse rounded bg-zinc-900" />
                  <div className="flex gap-1.5">
                    <div className="h-5 w-16 animate-pulse rounded-full bg-zinc-900" />
                    <div className="h-5 w-20 animate-pulse rounded-full bg-zinc-900" />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="overflow-hidden rounded-xl border border-zinc-800/80 bg-zinc-900/20">
        <div className="border-b border-zinc-800/70 px-5 py-5 md:px-6 md:py-6">
          <div className="flex items-start gap-4">
            <div className="h-11 w-11 shrink-0 animate-pulse rounded-xl bg-zinc-800" />
            <div className="w-full max-w-2xl space-y-3">
              <div className="h-3 w-28 animate-pulse rounded bg-zinc-800" />
              <div className="h-5 w-52 animate-pulse rounded bg-zinc-800" />
              <div className="h-3 w-full animate-pulse rounded bg-zinc-900" />
            </div>
          </div>
        </div>
        <div className="space-y-3 p-4 md:p-5">
          <div className="h-4 w-44 animate-pulse rounded bg-zinc-800" />
          <div className="overflow-hidden rounded-lg border border-zinc-800/80 bg-[#0d0d10]">
            {Array.from({ length: 7 }).map((_, index) => (
              <div key={index} className="grid gap-3 border-b border-zinc-900 px-4 py-3.5 last:border-b-0 md:grid-cols-[230px_minmax(0,1fr)]">
                <div className="flex items-center gap-3">
                  <div className="h-7 w-7 animate-pulse rounded-md bg-zinc-800" />
                  <div className="space-y-2">
                    <div className="h-3 w-32 animate-pulse rounded bg-zinc-800" />
                    <div className="h-4 w-14 animate-pulse rounded-full bg-zinc-900" />
                  </div>
                </div>
                <div className="space-y-2 md:pt-1">
                  <div className="h-3 w-full animate-pulse rounded bg-zinc-900" />
                  <div className="h-3 w-2/3 animate-pulse rounded bg-zinc-900" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

export default function ModeloSemanticoPage() {
  const router = useRouter();
  const [selectedId, setSelectedId] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("fields");
  const [isCreatingMetric, setIsCreatingMetric] = useState(false);
  const [draftMetricName, setDraftMetricName] = useState("");
  const [draftMetricGoal, setDraftMetricGoal] = useState("");
  const [draftMetricExpression, setDraftMetricExpression] = useState("");
  const [draftMetricDescription, setDraftMetricDescription] = useState("");
  const [draftMetricFormat, setDraftMetricFormat] = useState("number");
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [customMetrics, setCustomMetrics] = useState<SemanticMetric[]>([]);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [catalogStatus, setCatalogStatus] = useState("");
  const [connections, setConnections] = useState<CatalogConnection[]>([]);
  const [reviewConnection, setReviewConnection] = useState<CatalogConnection | null>(null);
  const [selectedConnectionId, setSelectedConnectionIdState] = useState(readStoredActiveConnectionId);
  const selectedConnectionIdRef = useRef(selectedConnectionId);
  const catalogRequestIdRef = useRef(0);
  const reviewRequestIdRef = useRef(0);
  const [catalogTables, setCatalogTables] = useState<CatalogTable[]>([]);
  const [catalogFields, setCatalogFields] = useState<CatalogField[]>([]);
  const [providerMetrics, setProviderMetrics] = useState<SemanticMetric[]>([]);
  const [isCatalogLoading, setIsCatalogLoading] = useState(true);
  const [expandedMetricKey, setExpandedMetricKey] = useState<string | null>(null);
  const [editingMetricId, setEditingMetricId] = useState<string | null>(null);
  const [editMetricName, setEditMetricName] = useState("");
  const [editMetricDescription, setEditMetricDescription] = useState("");
  const [editMetricExpression, setEditMetricExpression] = useState("");
  const [editMetricFormat, setEditMetricFormat] = useState("number");
  const [editStatusMessage, setEditStatusMessage] = useState("");
  const [isUpdatingMetric, setIsUpdatingMetric] = useState(false);
  const [isDeletingMetric, setIsDeletingMetric] = useState(false);
  const [editingFieldId, setEditingFieldId] = useState<string | null>(null);
  const [editFieldDescription, setEditFieldDescription] = useState("");
  const [fieldStatusMessage, setFieldStatusMessage] = useState("");
  const [isUpdatingField, setIsUpdatingField] = useState(false);

  const getAuthHeaders = useCallback(async (): Promise<Record<string, string>> => {
    return (await getSupabaseAuthHeaders()).headers;
  }, []);

  const setSelectedConnectionId = useCallback((connectionId: string, options?: { persist?: boolean }) => {
    selectedConnectionIdRef.current = connectionId;
    setSelectedConnectionIdState(connectionId);
    if (options?.persist) writeStoredActiveConnectionId(connectionId);
  }, []);

  const loadReviewConnection = useCallback(async (headers: Record<string, string>) => {
    if (!headers.Authorization) {
      setReviewConnection(null);
      return;
    }
    const requestId = ++reviewRequestIdRef.current;
    try {
      const response = await fetch(`${apiBaseUrl}/semantic-model/onboarding/review-connection`, { headers });
      if (requestId !== reviewRequestIdRef.current) return;
      if (response.ok) {
        const data = await response.json();
        const connection = data.connection as CatalogConnection | null;
        setReviewConnection(connection?.status === "review" ? connection : null);
      } else {
        setReviewConnection(null);
      }
    } catch {
      if (requestId === reviewRequestIdRef.current) setReviewConnection(null);
    }
  }, []);

  const loadCustomMetrics = useCallback(async (connectionId?: string) => {
    const effectiveConnectionId = connectionId ?? selectedConnectionIdRef.current;
    const requestId = ++catalogRequestIdRef.current;
    setIsCatalogLoading(true);
    setCatalogStatus("");
    try {
      const headers = await getAuthHeaders();
      const query = effectiveConnectionId ? `?connection_id=${encodeURIComponent(effectiveConnectionId)}` : "";
      const response = await fetch(`${apiBaseUrl}/semantic-model/catalog${query}`, { headers });
      if (requestId !== catalogRequestIdRef.current) return;
      if (!response.ok) {
        setCatalogStatus("No pude cargar indicadores guardados. Revisa que el servicio este disponible.");
        return;
      }
      const data = await response.json();
      const metrics = (data.metrics ?? [])
        .filter((metric: { source?: string }) => metric.source === "custom")
        .map((metric: { id?: string; key: string; name: string; description?: string; expression?: string; format?: string; business_formula?: string }) => ({
          id: metric.id,
          key: metric.key,
          name: metric.name,
          description: metric.description || "",
          definition: businessText(metric.business_formula || metric.description, "Indicador creado para analisis ejecutivo."),
          aggregation: "number" as const,
          format: metric.format,
          formula: metric.expression,
          source: "custom" as const,
      }));
      setCustomMetrics(metrics);
      const readyConnections = ((data.connections ?? []) as CatalogConnection[]).filter((connection) =>
        ["ready", "connected"].includes(connection.status),
      );
      setConnections(readyConnections);
      const nextConnectionId = data.selected_connection_id ?? effectiveConnectionId ?? "";
      setSelectedConnectionId(nextConnectionId, { persist: Boolean(nextConnectionId) });
      setCatalogTables(data.tables ?? []);
      setCatalogFields(data.fields ?? []);
      setProviderMetrics(
        (data.metrics ?? [])
          .filter((metric: { source?: string; model_id?: string }) => metric.source && metric.source !== "custom" && metric.model_id)
          .map((metric: { field_id?: string; key: string; name: string; description?: string; expression?: string; format?: string; business_formula?: string; source?: "cube" | "powerbi" | "excel"; model_id?: string }) => ({
            fieldId: metric.field_id,
            modelId: metric.model_id,
            key: metric.key,
            name: metric.name,
            description: metric.description || "",
            definition: businessText(metric.business_formula || metric.description, "Indicador base disponible para analisis ejecutivo."),
            aggregation: "number" as const,
            format: metric.format,
            formula: metric.expression,
            source: metric.source,
          }))
      );
      setCatalogStatus("");
      void loadReviewConnection(headers);
    } catch {
      if (requestId !== catalogRequestIdRef.current) return;
      setCustomMetrics([]);
      setCatalogTables([]);
      setCatalogFields([]);
      setProviderMetrics([]);
      setReviewConnection(null);
      setCatalogStatus("Servicio no disponible. Podes navegar el modelo, pero no crear indicadores por ahora.");
    } finally {
      if (requestId === catalogRequestIdRef.current) setIsCatalogLoading(false);
    }
  }, [getAuthHeaders, loadReviewConnection, setSelectedConnectionId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadCustomMetrics();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadCustomMetrics]);

  const remoteAreas = useMemo(() => {
    if (!catalogTables.length && !catalogFields.length && !providerMetrics.length) return [];
    const areaMap = new Map<string, SemanticArea>();

    const sourceLabel = (source?: string) => {
      return sourceDisplayName(source);
    };

    const sourceTone = (source?: string) => {
      if (source === "excel") return "from-emerald-400/15 to-lime-400/10";
      if (source === "powerbi") return "from-yellow-400/15 to-sky-400/10";
      return "from-zinc-300/10 to-sky-400/10";
    };

    const ensureArea = (tableName: string, modelId?: string, source?: string, displayName?: string): SemanticArea => {
      const id = `provider-${modelId || "model"}-${tableName.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
      const existing = areaMap.get(id);
      if (existing) return existing;
      const area: SemanticArea = {
        id,
        modelId,
        source,
        name: displayName || tableName,
        businessName: sourceLabel(source),
        summary: "Campos sincronizados desde el modelo semantico conectado.",
        icon: Network,
        tone: sourceTone(source),
        fields: [],
        metrics: [],
      };
      areaMap.set(id, area);
      return area;
    };

    catalogTables.forEach((table) => {
      const metadata = table.metadata ?? {};
      ensureArea(
        table.name,
        table.model_id,
        metadata.source,
        table.business_name || table.suggested_business_name || table.display_name || metadata.sheet_name || table.name,
      );
    });

    catalogFields
      .filter((field) => field.field_kind !== "measure" && field.is_ai_enabled !== false)
      .forEach((field) => {
        const [tableName] = field.semantic_key.split(".");
        const metadata = field.metadata ?? {};
        const type: FieldType = field.field_kind === "time" ? "fecha" : field.data_type?.toLowerCase().includes("int") || field.data_type?.toLowerCase().includes("decimal") ? "numero" : "texto";
        ensureArea(tableName || "Modelo", field.model_id, String(metadata.source || field.source || "") || undefined).fields.push({
          id: field.id,
          key: field.semantic_key,
          name: field.business_name || field.suggested_business_name || field.display_name || field.name,
          type,
          description: field.description || field.suggested_description || "",
        });
      });

    providerMetrics.forEach((metric) => {
      const [tableName] = metric.key.split(".");
      ensureArea(tableName || "Indicadores", metric.modelId, metric.source).metrics.push(metric);
    });

    return Array.from(areaMap.values());
  }, [catalogFields, catalogTables, providerMetrics]);

  const areas = useMemo(() => {
    const customArea: SemanticArea = {
      id: "metricas",
      name: "Indicadores creados",
      businessName: "Definiciones del usuario",
      summary: "Indicadores aprobados y disponibles para analisis, informes y asistentes.",
      icon: Calculator,
      tone: "from-emerald-400/15 to-zinc-100/10",
      fields: [],
      metrics: customMetrics,
    };
    const baseAreas = remoteAreas.length ? remoteAreas : [];
    return [...baseAreas, customArea];
  }, [customMetrics, remoteAreas]);

  const filteredAreas = useMemo(() => {
    const query = searchQuery.toLowerCase().trim();
    if (!query) return areas;

    return areas.filter((area) =>
      [
        area.name,
        area.businessName,
        area.summary,
        ...area.fields.flatMap((field) => [field.name, field.description]),
        ...area.metrics.flatMap((metric) => [metric.name, metric.description, metric.definition ?? ""]),
      ]
        .join(" ")
        .toLowerCase()
        .includes(query)
    );
  }, [areas, searchQuery]);

  const selectedArea = filteredAreas.find((area) => area.id === selectedId) ?? filteredAreas[0] ?? areas[0];

  const SelectedIcon = selectedArea.icon;
  const itemCount = viewMode === "fields" ? selectedArea.fields.length : selectedArea.metrics.length;
  const hasCatalogContent = Boolean(catalogTables.length || catalogFields.length || providerMetrics.length || customMetrics.length);
  const showCatalogLoading = isCatalogLoading && !hasCatalogContent;

  const validateFormula = async (expression = draftMetricExpression) => {
    setStatusMessage("");
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/semantic-model/metrics/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ name: draftMetricName, expression, connection_id: selectedConnectionIdRef.current || undefined }),
      });
      const result = await response.json();
      setValidation(result);
      return result as ValidationResult;
    } catch {
      const result: ValidationResult = {
        valid: false,
        error: "No pude preparar la definicion porque el servicio no esta disponible.",
      };
      setValidation(result);
      return result;
    }
  };

  const suggestMetric = async () => {
    if (!draftMetricGoal.trim()) return;
    setIsSuggesting(true);
    setStatusMessage("");
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/semantic-model/metrics/suggest`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({
          name: draftMetricName,
          goal: draftMetricGoal,
          connection_id: selectedConnectionIdRef.current || undefined,
        }),
      });
      if (!response.ok) {
        setStatusMessage("No pude generar la sugerencia. Revisa que el servicio este disponible.");
        return;
      }
      const suggestion = await response.json();
      setDraftMetricName(suggestion.name || draftMetricName);
      setDraftMetricDescription(suggestion.description || "");
      setDraftMetricExpression(suggestion.expression || "");
      setDraftMetricFormat(suggestion.format || "number");
      await validateFormula(suggestion.expression || "");
      setStatusMessage("Sugerencia generada. Revisa la descripcion y aproba el guardado.");
    } catch {
      setStatusMessage("No pude generar la sugerencia porque el servicio no esta disponible.");
    } finally {
      setIsSuggesting(false);
    }
  };

  const saveMetric = async () => {
    setIsSaving(true);
    setStatusMessage("");
    try {
      const headers = await getAuthHeaders();
      if (!headers.Authorization) {
        setStatusMessage("Necesitas iniciar sesion para guardar indicadores.");
        return;
      }
      const result = await validateFormula();
      if (!result.valid) return;

      const response = await fetch(`${apiBaseUrl}/semantic-model/metrics`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({
          name: draftMetricName,
          description: draftMetricDescription,
          expression: draftMetricExpression,
          format: draftMetricFormat,
          created_by_ai: Boolean(draftMetricGoal.trim()),
          connection_id: selectedConnectionIdRef.current || undefined,
        }),
      });
      if (!response.ok) {
        const error = await response.json();
        setStatusMessage(businessText(error.detail, "No se pudo guardar el indicador."));
        return;
      }
      setDraftMetricName("");
      setDraftMetricGoal("");
      setDraftMetricExpression("");
      setDraftMetricDescription("");
      setDraftMetricFormat("number");
      setValidation(null);
      setIsCreatingMetric(false);
      setSelectedId("metricas");
      setViewMode("metrics");
      setStatusMessage("Indicador aprobado y guardado.");
      await loadCustomMetrics();
    } catch {
      setStatusMessage("No pude guardar el indicador porque el servicio no esta disponible.");
    } finally {
      setIsSaving(false);
    }
  };

  const openMetricEditor = (metric: SemanticMetric) => {
    setEditingMetricId(metric.id ?? null);
    setEditMetricName(metric.name);
    setEditMetricDescription(metric.description);
    setEditMetricExpression(metric.formula ?? "");
    setEditMetricFormat(metric.format ?? "number");
    setEditStatusMessage("");
  };

  const closeMetricEditor = () => {
    setEditingMetricId(null);
    setEditStatusMessage("");
  };

  const updateMetric = async (metric: SemanticMetric) => {
    if (!metric.id) return;
    setIsUpdatingMetric(true);
    setEditStatusMessage("");
    try {
      const headers = await getAuthHeaders();
      if (!headers.Authorization) {
        setEditStatusMessage("Necesitas iniciar sesion para editar indicadores.");
        return;
      }

      const validationResponse = await fetch(`${apiBaseUrl}/semantic-model/metrics/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({
          name: editMetricName,
          expression: editMetricExpression,
          metric_id: metric.id,
          connection_id: selectedConnectionIdRef.current || undefined,
        }),
      });
      const validationResult = await validationResponse.json();
      if (!validationResult.valid) {
        setEditStatusMessage(businessText(validationResult.error, "La definicion no esta lista para guardar."));
        return;
      }

      const response = await fetch(`${apiBaseUrl}/semantic-model/metrics/${metric.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({
          name: editMetricName,
          description: editMetricDescription,
          expression: editMetricExpression,
          format: editMetricFormat,
          connection_id: selectedConnectionIdRef.current || undefined,
        }),
      });
      if (!response.ok) {
        const error = await response.json();
        setEditStatusMessage(businessText(error.detail, "No se pudo editar el indicador."));
        return;
      }
      setEditStatusMessage("Indicador actualizado.");
      closeMetricEditor();
      await loadCustomMetrics();
    } catch {
      setEditStatusMessage("No pude editar el indicador porque el servicio no esta disponible.");
    } finally {
      setIsUpdatingMetric(false);
    }
  };

  const deleteMetric = async (metric: SemanticMetric) => {
    if (!metric.id) return;
    if (!window.confirm(`Eliminar el indicador "${metric.name}"?`)) return;
    setIsDeletingMetric(true);
    setEditStatusMessage("");
    try {
      const headers = await getAuthHeaders();
      if (!headers.Authorization) {
        setEditStatusMessage("Necesitas iniciar sesion para eliminar indicadores.");
        return;
      }
      const response = await fetch(`${apiBaseUrl}/semantic-model/metrics/${metric.id}`, {
        method: "DELETE",
        headers,
      });
      if (!response.ok) {
        const error = await response.json();
        setEditStatusMessage(businessText(error.detail, "No se pudo eliminar el indicador."));
        return;
      }
      setEditingMetricId(null);
      setExpandedMetricKey(null);
      await loadCustomMetrics();
    } catch {
      setEditStatusMessage("No pude eliminar el indicador porque el servicio no esta disponible.");
    } finally {
      setIsDeletingMetric(false);
    }
  };

  const openFieldEditor = (field: SemanticField) => {
    if (!field.id) return;
    setEditingFieldId(field.id);
    setEditFieldDescription(field.description);
    setFieldStatusMessage("");
  };

  const closeFieldEditor = () => {
    setEditingFieldId(null);
    setEditFieldDescription("");
    setFieldStatusMessage("");
  };

  const updateFieldDescription = async (field: SemanticField) => {
    if (!field.id) return;
    setIsUpdatingField(true);
    setFieldStatusMessage("");
    try {
      const headers = await getAuthHeaders();
      if (!headers.Authorization) {
        setFieldStatusMessage("Necesitas iniciar sesion para editar campos.");
        return;
      }

      const response = await fetch(`${apiBaseUrl}/semantic-model/fields/${field.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ description: editFieldDescription }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        setFieldStatusMessage(error.detail || "No pude actualizar la descripcion.");
        return;
      }

      setCatalogFields((current) =>
        current.map((catalogField) =>
          catalogField.id === field.id
            ? { ...catalogField, description: editFieldDescription.trim() }
            : catalogField
        )
      );
      closeFieldEditor();
    } catch {
      setFieldStatusMessage("No pude actualizar la descripcion porque el servicio no esta disponible.");
    } finally {
      setIsUpdatingField(false);
    }
  };

  const updateMetricFieldDescription = async (metric: SemanticMetric) => {
    if (!metric.fieldId) return;
    setIsUpdatingField(true);
    setFieldStatusMessage("");
    try {
      const headers = await getAuthHeaders();
      if (!headers.Authorization) {
        setFieldStatusMessage("Necesitas iniciar sesion para editar campos.");
        return;
      }

      const response = await fetch(`${apiBaseUrl}/semantic-model/fields/${metric.fieldId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ description: editFieldDescription }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        setFieldStatusMessage(error.detail || "No pude actualizar la descripcion.");
        return;
      }

      const description = editFieldDescription.trim();
      setCatalogFields((current) =>
        current.map((catalogField) =>
          catalogField.id === metric.fieldId
            ? { ...catalogField, description }
            : catalogField
        )
      );
      setProviderMetrics((current) =>
        current.map((providerMetric) =>
          providerMetric.fieldId === metric.fieldId
            ? { ...providerMetric, description }
            : providerMetric
        )
      );
      closeFieldEditor();
    } catch {
      setFieldStatusMessage("No pude actualizar la descripcion porque el servicio no esta disponible.");
    } finally {
      setIsUpdatingField(false);
    }
  };

  return (
    <div className="flex h-full flex-1 flex-col overflow-y-auto bg-[#0a0a0c]">
      <div className="sticky top-0 z-40 flex flex-col items-stretch justify-between gap-3 border-b border-zinc-900/60 bg-[#0a0a0c]/95 px-4 py-4 backdrop-blur-xl md:flex-row md:items-center md:px-8">
        <div className="relative w-full md:w-80">
          <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            placeholder="Buscar campo o indicador..."
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            className="w-full rounded-full border border-zinc-800/80 bg-zinc-900/40 py-1.5 pl-9 pr-4 text-xs text-zinc-200 placeholder-zinc-500 transition-colors focus:border-zinc-700/80 focus:outline-none"
          />
        </div>

        <div className="hidden items-center gap-3 md:flex">
          <span className="text-xs text-zinc-500">Dashboard</span>
          <span className="select-none text-[10px] text-zinc-700">/</span>
          <span className="text-xs font-medium text-zinc-300">Modelo semantico</span>
        </div>
      </div>

      <div className="px-4 py-5 md:px-8 md:py-7">
        <div className="mb-7 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900">
              <Network size={16} className="text-zinc-300" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-zinc-100">Modelo semantico</h1>
              <p className="mt-1 max-w-2xl text-xs leading-relaxed text-zinc-500">
                Campos para agrupar y filtrar. Indicadores para calcular resultados aprobados.
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-2 md:items-end">
            {connections.length > 0 ? (
              <select
                value={selectedConnectionId}
                onChange={(event) => {
                  const id = event.target.value;
                  setSelectedConnectionId(id, { persist: true });
                  void loadCustomMetrics(id);
                }}
                className="h-8 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-300 outline-none focus:border-zinc-700"
              >
                <option value="">Todas las fuentes</option>
                {connections.map((connection) => (
                  <option key={connection.id} value={connection.id}>
                    {connection.config?.dataset_name || connection.config?.file_name || connection.name || "Fuente conectada"}
                  </option>
                ))}
              </select>
            ) : null}
            <div className="flex items-center gap-2 text-[11px] text-zinc-500">
              <ShieldCheck size={14} className="text-zinc-400" />
              <span>{showCatalogLoading ? "Cargando modelo" : `${areas.length} bloques conectados`}</span>
            </div>
          </div>
        </div>

        {catalogStatus ? (
          <div className="mb-4 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            {catalogStatus}
          </div>
        ) : null}

        {reviewConnection ? (
          <div className="mb-4 flex flex-col gap-3 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-xs text-emerald-100 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="font-medium">Excel en revision: {reviewConnection.config?.file_name || reviewConnection.name}</p>
              <p className="mt-0.5 text-emerald-200/70">El catalogo aparecera aca cuando termine la aprobacion.</p>
            </div>
            <button
              type="button"
              onClick={() => router.push(`/settings/conectores?excel_onboarding=${encodeURIComponent(reviewConnection.id)}`)}
              className="inline-flex h-8 shrink-0 items-center justify-center gap-2 rounded-md bg-emerald-100 px-3 font-medium text-emerald-950 transition-colors hover:bg-white"
            >
              <ShieldCheck size={13} />
              Continuar onboarding
            </button>
          </div>
        ) : null}

        {showCatalogLoading ? (
          <CatalogLoadingSkeleton />
        ) : (
          <div className="grid items-start gap-4 lg:grid-cols-[330px_minmax(0,1fr)]">
          <section className="self-start overflow-hidden rounded-xl border border-zinc-800/80 bg-zinc-900/20">
            <div className="flex items-center justify-between border-b border-zinc-800/70 px-4 py-3">
              <span className="text-xs font-medium text-zinc-300">Bloques de informacion</span>
              <span className="text-[10px] text-zinc-600">{filteredAreas.length}</span>
            </div>

            <div className="space-y-1.5 p-2">
              {filteredAreas.map((area) => {
                const Icon = area.icon;
                const isActive = area.id === selectedArea.id;

                return (
                  <button
                    key={area.id}
                    onClick={() => setSelectedId(area.id)}
                    className={`group w-full rounded-lg border px-3 py-3 text-left transition-all ${
                      isActive
                        ? "border-zinc-700 bg-zinc-800/60"
                        : "border-transparent hover:border-zinc-800 hover:bg-zinc-900/60"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border ${
                        isActive ? "border-zinc-600 bg-zinc-950" : "border-zinc-800 bg-zinc-950/60"
                      }`}>
                        <Icon size={15} className={isActive ? "text-zinc-100" : "text-zinc-500 group-hover:text-zinc-300"} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <h2 className="truncate text-sm font-medium text-zinc-100">{area.name}</h2>
                        <p className="mt-0.5 text-[11px] text-zinc-500">{area.businessName}</p>
                        <div className="mt-2 flex gap-1.5 text-[10px] text-zinc-500">
                          <span className="rounded-full border border-zinc-800 px-2 py-0.5">{area.fields.length} campos</span>
                          <span className="rounded-full border border-zinc-800 px-2 py-0.5">{area.metrics.length} indicadores</span>
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="overflow-hidden rounded-xl border border-zinc-800/80 bg-zinc-900/20">
            <div className={`border-b border-zinc-800/70 bg-gradient-to-br ${selectedArea.tone} px-5 py-5 md:px-6 md:py-6`}>
              <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
                <div className="flex items-start gap-4">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-zinc-700/70 bg-zinc-950/70">
                    <SelectedIcon size={20} className="text-zinc-100" />
                  </div>
                  <div>
                    <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-zinc-500">
                      {selectedArea.businessName}
                    </p>
                    <h2 className="mt-1 text-xl font-semibold text-zinc-50">{selectedArea.name}</h2>
                    <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-400">
                      {selectedArea.summary}
                    </p>
                  </div>
                </div>

                <div className="flex rounded-lg border border-zinc-700/70 bg-zinc-950/50 p-1">
                  {[
                    { id: "fields" as const, label: "Campos", icon: ListFilter },
                    { id: "metrics" as const, label: "Indicadores", icon: Calculator },
                  ].map(({ id, label, icon: Icon }) => (
                    <button
                      key={id}
                      onClick={() => setViewMode(id)}
                      className={`inline-flex h-8 items-center gap-2 rounded-md px-3 text-[11px] font-medium transition-colors ${
                        viewMode === id ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"
                      }`}
                    >
                      <Icon size={13} />
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="p-4 md:p-5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-medium text-zinc-200">
                    {viewMode === "fields" ? "Campos disponibles" : "Indicadores disponibles"}
                  </h3>
                  <p className="mt-0.5 text-[11px] text-zinc-600">
                    {viewMode === "fields"
                      ? "Los campos sirven para filtrar, agrupar o describir."
                      : "Los indicadores estan listos para informes, asistentes y tableros."}
                  </p>
                </div>
                <span className="shrink-0 text-[11px] text-zinc-500">{itemCount} items</span>
              </div>

              {viewMode === "fields" ? (
                <div className="overflow-hidden rounded-lg border border-zinc-800/80 bg-[#0d0d10]">
                  {selectedArea.fields.map((field) => {
                    const Icon = fieldIcon[field.type];
                    const isEditingField = editingFieldId === field.id;
                    const description = field.description || "Agrega una descripcion para darle contexto de negocio a la IA.";

                    return (
                      <div key={field.id ?? field.key} className="grid gap-3 border-b border-zinc-900 px-4 py-3.5 transition-colors last:border-b-0 hover:bg-zinc-900/50 md:grid-cols-[230px_minmax(0,1fr)] md:items-start">
                        <div className="flex min-w-0 items-center gap-3">
                          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-zinc-800 bg-zinc-950">
                            <Icon size={13} className="text-zinc-500" />
                          </div>
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium text-zinc-200">{field.name}</p>
                            <span className="mt-1 inline-flex rounded-full border border-zinc-800 px-2 py-0.5 text-[10px] text-zinc-500">
                              {field.type}
                            </span>
                          </div>
                        </div>
                        <div className="min-w-0 space-y-2 md:pt-1">
                          {isEditingField ? (
                            <div className="space-y-2">
                              <textarea
                                value={editFieldDescription}
                                onChange={(event) => setEditFieldDescription(event.target.value)}
                                placeholder="Describe que significa este campo y cuando usarlo."
                                rows={3}
                                className="w-full resize-none rounded-md border border-zinc-800 bg-zinc-950/80 px-3 py-2 text-xs leading-relaxed text-zinc-200 outline-none transition-colors placeholder:text-zinc-600 focus:border-zinc-700"
                              />
                              <div className="flex flex-wrap items-center gap-2">
                                <button
                                  type="button"
                                  onClick={() => updateFieldDescription(field)}
                                  disabled={isUpdatingField}
                                  className="inline-flex h-8 items-center gap-2 rounded-md bg-zinc-100 px-3 text-[11px] font-medium text-zinc-950 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  <Save size={13} />
                                  {isUpdatingField ? "Guardando..." : "Guardar"}
                                </button>
                                <button
                                  type="button"
                                  onClick={closeFieldEditor}
                                  className="inline-flex h-8 items-center gap-2 rounded-md border border-zinc-800 px-3 text-[11px] font-medium text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-zinc-200"
                                >
                                  <X size={13} />
                                  Cancelar
                                </button>
                                {fieldStatusMessage ? (
                                  <span className="text-[11px] text-amber-300">{fieldStatusMessage}</span>
                                ) : null}
                              </div>
                            </div>
                          ) : (
                            <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                              <p className={`text-xs leading-relaxed ${field.description ? "text-zinc-500" : "text-zinc-600"}`}>
                                {description}
                              </p>
                              {field.id ? (
                                <button
                                  type="button"
                                  onClick={() => openFieldEditor(field)}
                                  className="inline-flex h-8 shrink-0 items-center gap-2 rounded-md border border-zinc-800 px-3 text-[11px] font-medium text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-zinc-200"
                                >
                                  <Pencil size={13} />
                                  Describir
                                </button>
                              ) : null}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="space-y-3">
                  <button
                    onClick={() => setIsCreatingMetric((value) => !value)}
                    className="flex w-full items-center justify-between rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 text-left transition-colors hover:border-emerald-400/40 hover:bg-emerald-500/15"
                  >
                    <span className="flex items-center gap-3">
                      <span className="flex h-8 w-8 items-center justify-center rounded-md border border-emerald-400/25 bg-emerald-400/10">
                        <Plus size={15} className="text-emerald-300" />
                      </span>
                      <span>
                        <span className="block text-sm font-medium text-zinc-100">Crear indicador</span>
                        <span className="block text-[11px] text-zinc-500">Defini un indicador con asistencia.</span>
                      </span>
                    </span>
                    <WandSparkles size={15} className="text-emerald-300" />
                  </button>

                  {isCreatingMetric ? (
                    <div className="rounded-lg border border-zinc-800/80 bg-[#0d0d10] p-4">
                      <div className="mb-3 flex items-center gap-3">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-zinc-800 bg-zinc-950">
                          <Sparkles size={14} className="text-zinc-400" />
                        </div>
                        <h4 className="text-sm font-medium text-zinc-200">Asistente de indicador</h4>
                      </div>

                      <div className="grid gap-3">
                        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_160px]">
                          <label className="grid gap-1.5">
                            <span className="text-[11px] font-medium text-zinc-500">Nombre</span>
                            <input
                              value={draftMetricName}
                              onChange={(event) => setDraftMetricName(event.target.value)}
                              placeholder="Ej: Margen operativo"
                              className="rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none transition-colors placeholder:text-zinc-600 focus:border-zinc-700"
                            />
                          </label>

                          <label className="grid gap-1.5">
                            <span className="text-[11px] font-medium text-zinc-500">Formato</span>
                            <select
                              value={draftMetricFormat}
                              onChange={(event) => setDraftMetricFormat(event.target.value)}
                              className="rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none transition-colors focus:border-zinc-700"
                            >
                              <option value="number">Numero</option>
                              <option value="currency">Moneda</option>
                              <option value="percent">Porcentaje</option>
                              <option value="duration_days">Duracion (dias)</option>
                              <option value="duration_hours">Duracion (horas)</option>
                              <option value="duration_minutes">Duracion (minutos)</option>
                              <option value="duration_seconds">Duracion (segundos)</option>
                            </select>
                          </label>
                        </div>

                        <label className="grid gap-1.5">
                          <span className="text-[11px] font-medium text-zinc-500">Que queres medir?</span>
                          <textarea
                            value={draftMetricGoal}
                            onChange={(event) => setDraftMetricGoal(event.target.value)}
                            placeholder="Ej: Quiero calcular el margen bruto"
                            rows={2}
                            className="resize-none rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs leading-relaxed text-zinc-200 outline-none transition-colors placeholder:text-zinc-600 focus:border-zinc-700"
                          />
                        </label>

                        <div className="flex flex-wrap gap-2">
                          {metricTemplates.map((template) => (
                            <button
                              key={template}
                              onClick={() => setDraftMetricGoal(template)}
                              className="rounded-full border border-zinc-800 px-3 py-1 text-[10px] text-zinc-500 transition-colors hover:border-zinc-700 hover:text-zinc-300"
                            >
                              {template}
                            </button>
                          ))}
                        </div>

                        <button
                          type="button"
                          onClick={suggestMetric}
                          className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-zinc-800 bg-zinc-900 px-3 text-xs font-medium text-zinc-200 transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
                          disabled={!draftMetricGoal.trim() || isSuggesting}
                        >
                          <WandSparkles size={14} />
                          {isSuggesting ? "Generando..." : "Generar sugerencia con IA"}
                        </button>

                        <label className="grid gap-1.5">
                          <span className="text-[11px] font-medium text-zinc-500">Descripcion</span>
                          <input
                            value={draftMetricDescription}
                            onChange={(event) => setDraftMetricDescription(event.target.value)}
                            placeholder="Breve descripcion de negocio"
                            className="rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none transition-colors placeholder:text-zinc-600 focus:border-zinc-700"
                          />
                        </label>

                        {validation ? (
                          <div className={`flex items-start gap-2 rounded-md border px-3 py-2 text-xs ${
                            validation.valid
                              ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-200"
                              : "border-red-500/25 bg-red-500/10 text-red-200"
                          }`}>
                            {validation.valid ? <Check size={14} /> : <AlertCircle size={14} />}
                            <span>
                              {validation.valid
                                ? "Definicion lista para aprobar."
                                : businessText(validation.error, "No pude preparar la definicion del indicador.")}
                            </span>
                          </div>
                        ) : null}

                        {statusMessage ? (
                          <p className="text-xs text-zinc-500">{statusMessage}</p>
                        ) : null}

                        <div className="flex flex-col gap-2 sm:flex-row">
                          <button
                            type="button"
                            onClick={saveMetric}
                            className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-md bg-zinc-100 px-3 text-xs font-medium text-zinc-950 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
                            disabled={!draftMetricName.trim() || !draftMetricExpression.trim() || isSaving}
                          >
                            <ShieldCheck size={14} />
                            {isSaving ? "Guardando..." : "Aprobar y guardar"}
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : null}

                  {selectedArea.metrics.length > 0 ? (
                    <div className="overflow-hidden rounded-lg border border-zinc-800/80 bg-[#0d0d10]">
                      {selectedArea.metrics.map((metric) => {
                        const isExpanded = expandedMetricKey === metric.key;
                        const isCustom = metric.source === "custom";
                        const isEditing = isCustom && editingMetricId === metric.id;
                        const isEditingMetricField = Boolean(metric.fieldId && editingFieldId === metric.fieldId);

                        return (
                          <div key={metric.key} className="border-b border-zinc-900 last:border-b-0">
                            <button
                              type="button"
                              onClick={() => {
                                setExpandedMetricKey(isExpanded ? null : metric.key);
                                if (isExpanded) closeMetricEditor();
                              }}
                              className="grid w-full gap-3 px-4 py-3.5 text-left transition-colors hover:bg-zinc-900/50 md:grid-cols-[230px_minmax(0,1fr)_24px] md:items-start"
                            >
                              <div className="flex min-w-0 items-center gap-3">
                                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-zinc-800 bg-zinc-950">
                                  <CircleDollarSign size={13} className="text-zinc-500" />
                                </div>
                                <div className="min-w-0">
                                  <p className="truncate text-sm font-medium text-zinc-200">{metric.name}</p>
                                  <p className="mt-0.5 truncate text-[10px] text-zinc-600">
                                    {sourceDisplayName(metric.source)}
                                  </p>
                                </div>
                              </div>
                              <div className="space-y-1 md:pt-1">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="rounded-full border border-zinc-800 px-2 py-0.5 text-[10px] text-zinc-500">
                                    {isCustom ? "Aprobada" : aggregationLabel[metric.aggregation]}
                                  </span>
                                  <span className="rounded-full border border-zinc-800 px-2 py-0.5 text-[10px] text-zinc-500">
                                    {metric.definition || "Definicion aprobada"}
                                  </span>
                                </div>
                                <p className="text-xs leading-relaxed text-zinc-500">{metric.description}</p>
                              </div>
                              <ChevronDown
                                size={15}
                                className={`mt-1 text-zinc-600 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                              />
                            </button>

                            {isExpanded ? (
                              <div className="border-t border-zinc-900 bg-zinc-950/40 px-4 py-4">
                                {isEditing ? (
                                  <div className="grid gap-3">
                                    <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_160px]">
                                      <label className="grid gap-1.5">
                                        <span className="text-[11px] font-medium text-zinc-500">Nombre</span>
                                        <input
                                          value={editMetricName}
                                          onChange={(event) => setEditMetricName(event.target.value)}
                                          className="rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none transition-colors focus:border-zinc-700"
                                        />
                                      </label>
                                      <label className="grid gap-1.5">
                                        <span className="text-[11px] font-medium text-zinc-500">Formato</span>
                                        <select
                                          value={editMetricFormat}
                                          onChange={(event) => setEditMetricFormat(event.target.value)}
                                          className="rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none transition-colors focus:border-zinc-700"
                                        >
                                          <option value="number">Numero</option>
                                          <option value="currency">Moneda</option>
                                          <option value="percent">Porcentaje</option>
                                          <option value="duration_days">Duracion (dias)</option>
                                          <option value="duration_hours">Duracion (horas)</option>
                                          <option value="duration_minutes">Duracion (minutos)</option>
                                          <option value="duration_seconds">Duracion (segundos)</option>
                                        </select>
                                      </label>
                                    </div>

                                    <label className="grid gap-1.5">
                                      <span className="text-[11px] font-medium text-zinc-500">Descripcion</span>
                                      <input
                                        value={editMetricDescription}
                                        onChange={(event) => setEditMetricDescription(event.target.value)}
                                        className="rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none transition-colors focus:border-zinc-700"
                                      />
                                    </label>

                                    {editStatusMessage ? (
                                      <p className="text-xs text-zinc-500">{editStatusMessage}</p>
                                    ) : null}

                                    <div className="flex flex-col gap-2 sm:flex-row">
                                      <button
                                        type="button"
                                        onClick={() => updateMetric(metric)}
                                        disabled={!editMetricName.trim() || !editMetricExpression.trim() || isUpdatingMetric}
                                        className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-md bg-zinc-100 px-3 text-xs font-medium text-zinc-950 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
                                      >
                                        <Save size={14} />
                                        {isUpdatingMetric ? "Guardando..." : "Guardar cambios"}
                                      </button>
                                      <button
                                        type="button"
                                        onClick={closeMetricEditor}
                                        className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-md border border-zinc-800 px-3 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-900"
                                      >
                                        <X size={14} />
                                        Cancelar
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  <div className="space-y-3">
                                    <div className="grid gap-2 text-xs text-zinc-500 md:grid-cols-2">
                                      <div>
                                        <span className="block text-[10px] uppercase tracking-[0.14em] text-zinc-700">Origen</span>
                                        <span className="text-zinc-400">{sourceDisplayName(metric.source)}</span>
                                      </div>
                                      <div>
                                        <span className="block text-[10px] uppercase tracking-[0.14em] text-zinc-700">Formato</span>
                                        <span className="text-zinc-400">{metric.format ?? "number"}</span>
                                      </div>
                                      <div className="md:col-span-2">
                                        <span className="block text-[10px] uppercase tracking-[0.14em] text-zinc-700">Definicion</span>
                                        <span className="text-zinc-400">
                                          {metric.definition || metric.description || "Indicador disponible para analisis ejecutivo."}
                                        </span>
                                      </div>
                                    </div>

                                    {metric.fieldId ? (
                                      isEditingMetricField ? (
                                        <div className="space-y-2">
                                          <textarea
                                            value={editFieldDescription}
                                            onChange={(event) => setEditFieldDescription(event.target.value)}
                                            placeholder="Describe que significa este indicador y cuando usarlo."
                                            rows={3}
                                            className="w-full resize-none rounded-md border border-zinc-800 bg-zinc-950/80 px-3 py-2 text-xs leading-relaxed text-zinc-200 outline-none transition-colors placeholder:text-zinc-600 focus:border-zinc-700"
                                          />
                                          <div className="flex flex-wrap items-center gap-2">
                                            <button
                                              type="button"
                                              onClick={() => updateMetricFieldDescription(metric)}
                                              disabled={isUpdatingField}
                                              className="inline-flex h-8 items-center gap-2 rounded-md bg-zinc-100 px-3 text-[11px] font-medium text-zinc-950 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                                            >
                                              <Save size={13} />
                                              {isUpdatingField ? "Guardando..." : "Guardar descripcion"}
                                            </button>
                                            <button
                                              type="button"
                                              onClick={closeFieldEditor}
                                              className="inline-flex h-8 items-center gap-2 rounded-md border border-zinc-800 px-3 text-[11px] font-medium text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-zinc-200"
                                            >
                                              <X size={13} />
                                              Cancelar
                                            </button>
                                            {fieldStatusMessage ? (
                                              <span className="text-[11px] text-amber-300">{fieldStatusMessage}</span>
                                            ) : null}
                                          </div>
                                        </div>
                                      ) : (
                                        <div className="flex min-w-0 flex-col gap-2 rounded-md border border-zinc-900 bg-zinc-950/40 p-3 sm:flex-row sm:items-start sm:justify-between">
                                          <p className={`text-xs leading-relaxed ${metric.description ? "text-zinc-500" : "text-zinc-600"}`}>
                                            {metric.description || "Agrega una descripcion para darle contexto de negocio a la IA."}
                                          </p>
                                          <button
                                            type="button"
                                            onClick={() => {
                                              setEditingFieldId(metric.fieldId ?? null);
                                              setEditFieldDescription(metric.description);
                                              setFieldStatusMessage("");
                                            }}
                                            className="inline-flex h-8 shrink-0 items-center gap-2 rounded-md border border-zinc-800 px-3 text-[11px] font-medium text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-zinc-200"
                                          >
                                            <Pencil size={13} />
                                            Describir
                                          </button>
                                        </div>
                                      )
                                    ) : null}

                                    {isCustom ? (
                                      <>
                                        {editStatusMessage ? (
                                          <p className="text-xs text-zinc-500">{editStatusMessage}</p>
                                        ) : null}
                                        <div className="flex flex-col gap-2 sm:flex-row">
                                          <button
                                            type="button"
                                            onClick={() => openMetricEditor(metric)}
                                            className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-md border border-zinc-800 px-3 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-900"
                                          >
                                            <Save size={14} />
                                            Editar
                                          </button>
                                          <button
                                            type="button"
                                            onClick={() => deleteMetric(metric)}
                                            disabled={isDeletingMetric}
                                            className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 text-xs font-medium text-red-200 transition-colors hover:bg-red-500/15 disabled:cursor-not-allowed disabled:opacity-40"
                                          >
                                            <Trash2 size={14} />
                                            {isDeletingMetric ? "Eliminando..." : "Eliminar"}
                                          </button>
                                        </div>
                                      </>
                                    ) : (
                                      !metric.fieldId ? (
                                        <p className="text-xs text-zinc-600">
                                          Este indicador pertenece al modelo base y no se edita desde esta vista.
                                        </p>
                                      ) : null
                                    )}
                                  </div>
                                )}
                              </div>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="rounded-lg border border-dashed border-zinc-800 bg-[#0d0d10] px-4 py-8 text-center">
                      <Calculator size={18} className="mx-auto text-zinc-600" />
                      <p className="mt-3 text-sm font-medium text-zinc-300">Este bloque no define indicadores propios.</p>
                      <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-zinc-600">
                        Puede usarse como contexto para segmentar indicadores de otros bloques.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>
          </div>
        )}
      </div>
    </div>
  );
}
