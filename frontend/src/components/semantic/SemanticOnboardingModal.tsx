"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  CircleDollarSign,
  Clock3,
  Database,
  Hash,
  Loader2,
  Sparkles,
  Text,
  WandSparkles,
  X,
} from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { getSupabaseAuthHeaders } from "@/lib/supabase/auth";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CARD_RENDER_STYLE: CSSProperties = { contentVisibility: "auto", containIntrinsicSize: "132px" };

type ApprovalStatus = "review" | "approved" | "rejected";
type DraftStatus = "draft" | "approved" | "rejected";

type CompanyContext = {
  company_name?: string;
  sector?: string;
  details?: string;
  complete?: boolean;
};

type OnboardingField = {
  id: string;
  semantic_key: string;
  name: string;
  display_name?: string;
  business_area?: string;
  business_name?: string;
  suggested_business_name?: string;
  description?: string;
  suggested_description?: string;
  effective_name?: string;
  effective_description?: string;
  field_kind: "measure" | "dimension" | "time" | "id" | "unknown";
  data_type?: string;
  approval_status?: ApprovalStatus;
  metadata?: {
    sheet_name?: string;
    profile?: {
      inferred_type?: string;
      null_count?: number;
      approx_distinct?: number;
      min?: string | number;
      max?: string | number;
      samples?: Array<string | number | boolean>;
    };
  };
};

type OnboardingMetric = {
  field_id?: string | null;
  key: string;
  name: string;
  business_area?: string;
  business_formula?: string;
  description?: string;
  expression?: string;
  source?: string;
  approval_status?: ApprovalStatus;
};

type MetricDraft = {
  id: string;
  name: string;
  description?: string;
  expression?: string | Record<string, unknown>;
  compiled_payload?: {
    formula_explanation?: string;
    business_formula?: string;
    format?: string;
  };
  status: DraftStatus;
};

type OnboardingPayload = {
  connection_id?: string | null;
  connection?: { id?: string; name?: string; status?: string } | null;
  company_context?: CompanyContext;
  tables?: Array<{
    id: string;
    display_name?: string;
    business_name?: string;
    metadata?: { row_count?: number; sheet_name?: string };
  }>;
  fields?: OnboardingField[];
  metrics?: OnboardingMetric[];
  drafts?: MetricDraft[];
  approval_summary?: {
    total: number;
    approved: number;
    pending: number;
  };
};

type Props = {
  isOpen: boolean;
  connectionId: string | null;
  selectedFile: File | null;
  onClose: () => void;
  onCompleted: (connectionId: string) => void;
  onRetryUpload?: () => Promise<void>;
};

async function readApiMessage(response: Response, fallback: string) {
  try {
    const payload = await response.json();
    if (typeof payload?.detail?.message === "string") return payload.detail.message;
    if (typeof payload?.detail === "string") return payload.detail;
    if (typeof payload?.message === "string") return payload.message;
  } catch {
    return fallback;
  }
  return fallback;
}

function isNumericField(field: OnboardingField) {
  return ["number", "integer", "decimal", "float", "double"].includes((field.data_type || "").toLowerCase());
}

function renderFieldIcon(field: OnboardingField, className: string) {
  if (field.field_kind === "time" || field.data_type === "date") return <Clock3 size={15} className={className} />;
  if (isNumericField(field)) return <Hash size={15} className={className} />;
  return <Text size={15} className={className} />;
}

function statusLabel(status?: ApprovalStatus | DraftStatus) {
  if (status === "approved") return "Aprobado";
  if (status === "rejected") return "Rechazado";
  if (status === "draft") return "Sugerido";
  return "Revision";
}

function hasTechnicalMarker(value?: string) {
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
  if (!text || hasTechnicalMarker(text)) return fallback;
  return text;
}

function fieldTitle(field: OnboardingField) {
  const fallback = field.field_kind === "time" ? "Fecha" : isNumericField(field) ? "Valor numerico" : "Concepto de negocio";
  return businessText(
    field.suggested_business_name || field.business_name || field.effective_name || field.display_name || field.name,
    fallback,
  );
}

function fieldArea(field: OnboardingField) {
  return businessText(field.business_area || field.metadata?.sheet_name, "Area de negocio");
}

function fieldDescription(field: OnboardingField) {
  return businessText(
    field.suggested_description || field.effective_description || field.description,
    "Concepto disponible para analisis ejecutivo.",
  );
}

function fieldTypeLabel(field: OnboardingField) {
  const dataType = (field.metadata?.profile?.inferred_type || field.data_type || field.field_kind || "").toLowerCase();
  if (field.field_kind === "time" || dataType.includes("date") || dataType.includes("time")) return "Fecha";
  if (isNumericField(field) || ["integer", "decimal", "float", "double", "number", "numeric"].includes(dataType)) return "Numero";
  return "Texto";
}

function fieldApprovalPayload(field: OnboardingField) {
  return {
    business_name: field.suggested_business_name || field.business_name || field.display_name || field.name,
    description: field.suggested_description || field.description || "",
    approval_status: "approved" as const,
  };
}

function metricTitle(metric: OnboardingMetric) {
  return businessText(metric.name, "Indicador de negocio");
}

function metricArea(metric: OnboardingMetric) {
  return businessText(metric.business_area, "Indicador ejecutivo");
}

function metricDescription(metric: OnboardingMetric) {
  return businessText(metric.description || metric.business_formula, "Indicador base listo para revision.");
}

function metricDefinition(metric: OnboardingMetric) {
  return businessText(metric.business_formula || metric.description, "Calculo preparado para analisis ejecutivo.");
}

function draftExplanation(draft: MetricDraft) {
  return businessText(
    draft.compiled_payload?.business_formula || draft.compiled_payload?.formula_explanation || draft.description,
    "Explicacion ejecutiva lista para revisar.",
  );
}

export function SemanticOnboardingModal({
  isOpen,
  connectionId,
  selectedFile,
  onClose,
  onCompleted,
  onRetryUpload,
}: Props) {
  const supabase = useMemo(() => createClient(), []);
  const [payload, setPayload] = useState<OnboardingPayload | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSavingContext, setIsSavingContext] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [isSuggestingMetrics, setIsSuggestingMetrics] = useState(false);
  const [isCompleting, setIsCompleting] = useState(false);
  const [activePhase, setActivePhase] = useState<"context" | "fields" | "metrics" | "done">("fields");
  const [status, setStatus] = useState("");
  const hasLoadedPayloadRef = useRef(false);
  const [companyForm, setCompanyForm] = useState({
    company_name: "",
    sector: "",
    details: "",
  });

  const loadCompanyContext = useCallback(async () => {
    const { data: userData } = await supabase.auth.getUser();
    const userId = userData.user?.id;
    if (!userId) return;
    const { data } = await supabase
      .from("company_settings")
      .select("company_name, sector, details")
      .eq("id", userId)
      .maybeSingle();
    const context = (data ?? {}) as CompanyContext;
    setCompanyForm({
      company_name: context.company_name ?? "",
      sector: context.sector ?? "",
      details: context.details ?? "",
    });
  }, [supabase]);

  const loadOnboarding = useCallback(async (options?: { quiet?: boolean }) => {
    if (!connectionId) {
      setPayload(null);
      hasLoadedPayloadRef.current = false;
      setActivePhase("context");
      await loadCompanyContext();
      return true;
    }
    setIsLoading(true);
    if (!options?.quiet) setStatus("");
    try {
      const { headers } = await getSupabaseAuthHeaders();
      const response = await fetch(
        `${apiBaseUrl}/semantic-model/onboarding?connection_id=${encodeURIComponent(connectionId)}`,
        { headers },
      );
      if (!response.ok) {
        if (!options?.quiet) {
          setStatus(await readApiMessage(response, "No pude cargar el onboarding semantico."));
        }
        return false;
      }
      const data = (await response.json()) as OnboardingPayload;
      setPayload(data);
      hasLoadedPayloadRef.current = true;
      const context = data.company_context ?? {};
      setCompanyForm({
        company_name: context.company_name ?? "",
        sector: context.sector ?? "",
        details: context.details ?? "",
      });
      if (!context.complete) {
        setActivePhase("context");
      } else if ((data.fields ?? []).some((field) => field.approval_status !== "approved")) {
        setActivePhase("fields");
      } else if ((data.metrics ?? []).some((metric) => metric.approval_status !== "approved")) {
        setActivePhase("metrics");
      } else {
        setActivePhase("metrics");
      }
      return true;
    } catch {
      if (!options?.quiet) {
        setStatus(
          hasLoadedPayloadRef.current
            ? "No pude actualizar la vista. El cambio quedo aplicado."
            : "No pude cargar el onboarding semantico.",
        );
      }
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [connectionId, loadCompanyContext]);

  useEffect(() => {
    if (!isOpen) return;
    const timer = window.setTimeout(() => {
      void loadOnboarding();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [isOpen, loadOnboarding]);

  const fields = useMemo(() => payload?.fields ?? [], [payload?.fields]);
  const metrics = useMemo(() => payload?.metrics ?? [], [payload?.metrics]);
  const drafts = useMemo(() => payload?.drafts ?? [], [payload?.drafts]);
  const pendingFields = useMemo(
    () => fields.filter((field) => field.approval_status !== "approved"),
    [fields],
  );
  const pendingMetrics = useMemo(
    () => metrics.filter((metric) => metric.approval_status !== "approved" && metric.field_id),
    [metrics],
  );
  const approvedDraftCount = useMemo(
    () => drafts.filter((draft) => draft.status === "approved").length,
    [drafts],
  );
  const pendingDraftCount = useMemo(
    () => drafts.filter((draft) => draft.status === "draft").length,
    [drafts],
  );
  const approvedCount = (payload?.approval_summary?.approved ?? 0) + approvedDraftCount;
  const pendingCount = pendingFields.length + pendingMetrics.length + pendingDraftCount;
  const canSaveContext = companyForm.sector.trim().length > 1 && companyForm.details.trim().length > 8;

  const markFieldsApproved = useCallback((fieldIds: string[]) => {
    const approvedIds = new Set(fieldIds);
    if (!approvedIds.size) return;
    setPayload((current) => {
      if (!current) return current;
      const newlyApprovedIds = new Set<string>();
      const nextFields = (current.fields ?? []).map((field) => {
        if (!approvedIds.has(field.id)) return field;
        if (field.approval_status !== "approved") newlyApprovedIds.add(field.id);
        return {
          ...field,
          ...fieldApprovalPayload(field),
          approval_status: "approved" as const,
        };
      });
      const nextMetrics = (current.metrics ?? []).map((metric) => {
        if (!metric.field_id || !approvedIds.has(metric.field_id)) return metric;
        if (metric.approval_status !== "approved") newlyApprovedIds.add(metric.field_id);
        return {
          ...metric,
          approval_status: "approved" as const,
        };
      });
      return {
        ...current,
        fields: nextFields,
        metrics: nextMetrics,
        approval_summary: current.approval_summary
          ? {
              ...current.approval_summary,
              approved: current.approval_summary.approved + newlyApprovedIds.size,
              pending: Math.max(0, current.approval_summary.pending - newlyApprovedIds.size),
            }
          : current.approval_summary,
      };
    });
  }, []);

  const saveCompanyContext = async () => {
    if (!canSaveContext) return;
    setIsSavingContext(true);
    setStatus("");
    try {
      const { data: userData } = await supabase.auth.getUser();
      const userId = userData.user?.id;
      if (!userId) {
        setStatus("Necesitas iniciar sesion para guardar el contexto.");
        return;
      }
      const { error } = await supabase.from("company_settings").upsert({
        id: userId,
        company_name: companyForm.company_name.trim(),
        sector: companyForm.sector.trim(),
        details: companyForm.details.trim(),
        updated_at: new Date().toISOString(),
      });
      if (error) {
        setStatus("No pude guardar el contexto de empresa.");
        return;
      }
      if (!connectionId && selectedFile && onRetryUpload) {
        setStatus("Contexto guardado. Procesando workbook...");
        await onRetryUpload();
        return;
      }
      await loadOnboarding();
      setActivePhase("fields");
    } catch {
      setStatus("No pude guardar el contexto de empresa.");
    } finally {
      setIsSavingContext(false);
    }
  };

  const approveField = async (field: OnboardingField) => {
    setStatus("");
    const { headers } = await getSupabaseAuthHeaders();
    const response = await fetch(`${apiBaseUrl}/semantic-model/fields/${field.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify(fieldApprovalPayload(field)),
    });
    if (!response.ok) {
      throw new Error(await readApiMessage(response, "No pude aprobar el campo."));
    }
  };

  const approveFieldsBatch = async (fieldsToApprove: OnboardingField[]) => {
    const fieldIds = fieldsToApprove.map((field) => field.id).filter(Boolean);
    if (!fieldIds.length) return fieldIds;
    const { headers } = await getSupabaseAuthHeaders();
    for (let index = 0; index < fieldIds.length; index += 500) {
      const response = await fetch(`${apiBaseUrl}/semantic-model/fields/approve-batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ field_ids: fieldIds.slice(index, index + 500) }),
      });
      if (!response.ok) {
        throw new Error(await readApiMessage(response, "No pude aprobar los campos."));
      }
    }
    return fieldIds;
  };

  const approveAllFields = async () => {
    if (!pendingFields.length) {
      setActivePhase("metrics");
      return;
    }
    setIsApproving(true);
    setStatus("");
    try {
      const approvedIds = await approveFieldsBatch(pendingFields);
      markFieldsApproved(approvedIds);
      setActivePhase("metrics");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "No pude aprobar los campos.");
    } finally {
      setIsApproving(false);
    }
  };

  const approveSingleField = async (field: OnboardingField) => {
    setIsApproving(true);
    setStatus("");
    try {
      await approveField(field);
      markFieldsApproved([field.id]);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "No pude aprobar el campo.");
    } finally {
      setIsApproving(false);
    }
  };

  const approveMetric = async (metric: OnboardingMetric) => {
    if (!metric.field_id) return;
    setIsApproving(true);
    setStatus("");
    try {
      const field = fields.find((item) => item.id === metric.field_id);
      if (field) await approveField(field);
      else {
        const { headers } = await getSupabaseAuthHeaders();
        const response = await fetch(`${apiBaseUrl}/semantic-model/fields/${metric.field_id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json", ...headers },
          body: JSON.stringify({ approval_status: "approved", description: metric.description || "" }),
        });
        if (!response.ok) throw new Error(await readApiMessage(response, "No pude aprobar el indicador base."));
      }
      markFieldsApproved([metric.field_id]);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "No pude aprobar el indicador base.");
    } finally {
      setIsApproving(false);
    }
  };

  const suggestMetrics = async () => {
    if (!connectionId) return;
    setIsSuggestingMetrics(true);
    setStatus("");
    try {
      const { headers } = await getSupabaseAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/semantic-model/onboarding/metrics/suggest`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ connection_id: connectionId, limit: 6 }),
      });
      if (!response.ok) {
        setStatus(await readApiMessage(response, "No pude generar indicadores sugeridos."));
        return;
      }
      const refreshed = await loadOnboarding({ quiet: true });
      setStatus(
        refreshed
          ? "Indicadores sugeridos generados."
          : "Indicadores sugeridos generados. Actualiza la vista para verlos.",
      );
    } catch {
      setStatus("No pude generar indicadores sugeridos.");
    } finally {
      setIsSuggestingMetrics(false);
    }
  };

  const updateDraft = async (draftId: string, action: "approve" | "reject") => {
    setIsApproving(true);
    setStatus("");
    try {
      const { headers } = await getSupabaseAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/semantic-metrics/drafts/${draftId}/${action}`, {
        method: "POST",
        headers,
      });
      if (!response.ok) {
        setStatus(await readApiMessage(response, "No pude actualizar la sugerencia."));
        return;
      }
      const refreshed = await loadOnboarding({ quiet: true });
      if (!refreshed) setStatus("Sugerencia actualizada. Actualiza la vista para ver los cambios.");
    } catch {
      setStatus("No pude actualizar la sugerencia.");
    } finally {
      setIsApproving(false);
    }
  };

  const completeOnboarding = async () => {
    if (!connectionId) return;
    setIsCompleting(true);
    setStatus("");
    try {
      const { headers } = await getSupabaseAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/semantic-model/onboarding/${connectionId}/complete`, {
        method: "POST",
        headers,
      });
      if (!response.ok) {
        setStatus(await readApiMessage(response, "Quedan elementos sin aprobar."));
        return;
      }
      setActivePhase("done");
      onCompleted(connectionId);
    } catch {
      setStatus("No pude completar el onboarding.");
    } finally {
      setIsCompleting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="semantic-onboarding fixed inset-0 z-[80] bg-[#060607] text-zinc-100">
      <div className="flex h-full flex-col">
        <header className="flex min-h-16 items-center justify-between border-b border-zinc-900 bg-[#09090a]/95 px-4 md:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950">
              <Database size={16} className="text-zinc-300" />
            </span>
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold text-zinc-50">Onboarding semantico</h2>
              <p className="truncate text-[11px] text-zinc-500">{selectedFile?.name || payload?.connection?.name || "Datos en revision"}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <PhasePill label="Contexto" active={activePhase === "context"} done={Boolean(payload?.company_context?.complete)} />
            <PhasePill label="Campos" active={activePhase === "fields"} done={pendingFields.length === 0 && fields.length > 0} />
            <PhasePill label="Indicadores" active={activePhase === "metrics"} done={pendingMetrics.length === 0 && metrics.length > 0} />
            <button
              type="button"
              onClick={onClose}
              className="ml-1 flex size-8 items-center justify-center rounded-full border border-zinc-800 text-zinc-500 transition-colors hover:bg-zinc-900 hover:text-zinc-200"
              aria-label="Cerrar"
            >
              <X size={15} />
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto px-4 py-5 md:px-6 md:py-6">
          <div className="mx-auto grid w-full max-w-7xl gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
            <aside className="self-start rounded-lg border border-zinc-800/80 bg-zinc-950/45 p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-zinc-300">Estado</span>
                {isLoading ? <Loader2 size={14} className="animate-spin text-zinc-500" /> : null}
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2">
                <Stat label="Aprobados" value={approvedCount} />
                <Stat label="Pendientes" value={pendingCount} />
              </div>
              <div className="mt-4 space-y-2 text-[11px] text-zinc-500">
                {(payload?.tables ?? []).slice(0, 6).map((table) => (
                  <div key={table.id} className="flex items-center justify-between gap-3 rounded-md border border-zinc-900 bg-black/20 px-2.5 py-2">
                    <span className="truncate">{table.business_name || table.display_name || table.metadata?.sheet_name}</span>
                    <span className="shrink-0 text-zinc-600">{table.metadata?.row_count ?? 0}</span>
                  </div>
                ))}
              </div>
              {status ? (
                <p className="mt-4 rounded-md border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-amber-200">
                  {status}
                </p>
              ) : null}
            </aside>

            <section className="min-w-0">
              {activePhase === "context" ? (
                <CompanyContextStep
                  form={companyForm}
                  onChange={setCompanyForm}
                  canSave={canSaveContext}
                  isSaving={isSavingContext}
                  onSave={saveCompanyContext}
                />
              ) : activePhase === "fields" ? (
                <ReviewSection
                  eyebrow="Mapa de negocio"
                  title="Conceptos detectados"
                  description={`${fields.length} conceptos listos para validar.`}
                  action={
                    <button
                      type="button"
                      onClick={approveAllFields}
                      disabled={isApproving || fields.length === 0}
                      className="inline-flex h-9 items-center gap-2 rounded-md bg-zinc-100 px-3 text-xs font-medium text-zinc-950 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {isApproving ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                      Aprobar conceptos
                    </button>
                  }
                >
                  <div className="grid gap-2 lg:grid-cols-2 2xl:grid-cols-3">
                    {fields.map((field) => (
                      <FieldCard key={field.id} field={field} onApprove={() => approveSingleField(field)} />
                    ))}
                  </div>
                </ReviewSection>
              ) : activePhase === "metrics" ? (
                <ReviewSection
                  eyebrow="Gobernanza de indicadores"
                  title="Indicadores sugeridos"
                  description={`${metrics.length} indicadores base listos. Las sugerencias aprobadas quedan disponibles para analisis e informes.`}
                  action={
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={suggestMetrics}
                        disabled={isSuggestingMetrics || pendingMetrics.length > 0}
                        className="inline-flex h-9 items-center gap-2 rounded-md border border-zinc-800 px-3 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-900 disabled:cursor-not-allowed disabled:opacity-45"
                      >
                        {isSuggestingMetrics ? <Loader2 size={14} className="animate-spin" /> : <WandSparkles size={14} />}
                        Sugerir indicadores
                      </button>
                      <button
                        type="button"
                        onClick={completeOnboarding}
                        disabled={isCompleting || pendingFields.length > 0 || pendingMetrics.length > 0}
                        className="inline-flex h-9 items-center gap-2 rounded-md bg-zinc-100 px-3 text-xs font-medium text-zinc-950 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isCompleting ? <Loader2 size={14} className="animate-spin" /> : <ArrowRight size={14} />}
                        Completar
                      </button>
                    </div>
                  }
                >
                  <div className="grid gap-2 lg:grid-cols-2 2xl:grid-cols-3">
                    {metrics.map((metric) => (
                      <MetricCard
                        key={metric.key}
                        metric={metric}
                        onApprove={() => approveMetric(metric)}
                      />
                    ))}
                    {drafts.map((draft) => (
                      <DraftCard
                        key={draft.id}
                        draft={draft}
                        onApprove={() => updateDraft(draft.id, "approve")}
                        onReject={() => updateDraft(draft.id, "reject")}
                      />
                    ))}
                  </div>
                </ReviewSection>
              ) : (
                <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-5">
                  <div className="flex items-center gap-3">
                    <span className="flex size-9 items-center justify-center rounded-full border border-emerald-400/30 bg-emerald-400/10">
                      <Check size={16} className="text-emerald-200" />
                    </span>
                    <div>
                      <h3 className="text-sm font-semibold text-emerald-100">Modelo listo</h3>
                      <p className="mt-1 text-xs text-emerald-200/75">Los conceptos aprobados ya estan disponibles para analisis e informes.</p>
                    </div>
                  </div>
                </div>
              )}
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}

function PhasePill({ label, active, done }: { label: string; active: boolean; done: boolean }) {
  return (
    <span
      className={`hidden h-7 items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-medium sm:inline-flex ${
        active
          ? "border-zinc-600 bg-zinc-800 text-zinc-100"
          : done
            ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-200"
            : "border-zinc-800 bg-zinc-950 text-zinc-500"
      }`}
    >
      {done ? <Check size={11} /> : null}
      {label}
    </span>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-zinc-900 bg-black/25 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-zinc-600">{label}</div>
      <div className="mt-1 text-lg font-semibold text-zinc-100">{value}</div>
    </div>
  );
}

function CompanyContextStep({
  form,
  onChange,
  canSave,
  isSaving,
  onSave,
}: {
  form: { company_name: string; sector: string; details: string };
  onChange: (value: { company_name: string; sector: string; details: string }) => void;
  canSave: boolean;
  isSaving: boolean;
  onSave: () => void;
}) {
  return (
    <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/45 p-5">
      <div className="mb-5">
        <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-zinc-600">Contexto de empresa</p>
        <h3 className="mt-2 text-lg font-semibold text-zinc-50">Perfil requerido</h3>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="grid gap-1.5">
          <span className="text-[11px] font-medium text-zinc-500">Empresa</span>
          <input
            value={form.company_name}
            onChange={(event) => onChange({ ...form, company_name: event.target.value })}
            className="h-10 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none transition-colors focus:border-zinc-700"
          />
        </label>
        <label className="grid gap-1.5">
          <span className="text-[11px] font-medium text-zinc-500">Sector</span>
          <input
            value={form.sector}
            onChange={(event) => onChange({ ...form, sector: event.target.value })}
            className="h-10 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none transition-colors focus:border-zinc-700"
          />
        </label>
        <label className="grid gap-1.5 md:col-span-2">
          <span className="text-[11px] font-medium text-zinc-500">Descripcion y objetivos</span>
          <textarea
            value={form.details}
            onChange={(event) => onChange({ ...form, details: event.target.value })}
            rows={5}
            className="resize-none rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm leading-relaxed text-zinc-100 outline-none transition-colors focus:border-zinc-700"
          />
        </label>
      </div>
      <div className="mt-5 flex justify-end">
        <button
          type="button"
          onClick={onSave}
          disabled={!canSave || isSaving}
          className="inline-flex h-9 items-center gap-2 rounded-md bg-zinc-100 px-3 text-xs font-medium text-zinc-950 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSaving ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
          Guardar contexto
        </button>
      </div>
    </div>
  );
}

function ReviewSection({
  eyebrow,
  title,
  description,
  action,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/35">
      <div className="flex flex-col gap-4 border-b border-zinc-900 px-4 py-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-zinc-600">{eyebrow}</p>
          <h3 className="mt-2 text-lg font-semibold text-zinc-50">{title}</h3>
          <p className="mt-1 text-xs text-zinc-500">{description}</p>
        </div>
        {action}
      </div>
      <div className="p-3 md:p-4">{children}</div>
    </div>
  );
}

function FieldCard({ field, onApprove }: { field: OnboardingField; onApprove: () => void }) {
  const approved = field.approval_status === "approved";
  const profile = field.metadata?.profile;
  const iconClass = approved ? "text-emerald-200" : "text-zinc-400";
  return (
    <article className={`rounded-lg border px-3 py-3 transition-colors ${
      approved ? "border-emerald-500/20 bg-emerald-500/[0.06]" : "border-zinc-800 bg-[#101012] hover:border-zinc-700"
    }`} style={CARD_RENDER_STYLE}>
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950">
          {renderFieldIcon(field, iconClass)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h4 className="truncate text-sm font-semibold text-zinc-100">{fieldTitle(field)}</h4>
              <p className="mt-0.5 truncate text-[10px] text-zinc-600">{fieldArea(field)}</p>
            </div>
            <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] ${
              approved ? "border-emerald-500/25 text-emerald-200" : "border-zinc-700 text-zinc-500"
            }`}>
              {statusLabel(field.approval_status)}
            </span>
          </div>
          <p className="mt-3 line-clamp-3 min-h-12 text-xs leading-relaxed text-zinc-400">
            {fieldDescription(field)}
          </p>
          <div className="mt-3 flex items-center justify-between gap-3">
            <div className="flex min-w-0 gap-1.5 text-[10px] text-zinc-600">
              <span className="rounded-full border border-zinc-800 px-2 py-0.5">{fieldTypeLabel(field)}</span>
              {profile?.approx_distinct !== undefined ? (
                <span className="rounded-full border border-zinc-800 px-2 py-0.5">{profile.approx_distinct} valores</span>
              ) : null}
            </div>
            {!approved ? (
              <button
                type="button"
                onClick={onApprove}
                className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md bg-zinc-100 px-2.5 text-[11px] font-medium text-zinc-950 transition-colors hover:bg-white"
              >
                <Check size={12} />
                Aprobar
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </article>
  );
}

function MetricCard({ metric, onApprove }: { metric: OnboardingMetric; onApprove: () => void }) {
  const approved = metric.approval_status === "approved" || !metric.field_id;
  return (
    <article className={`rounded-lg border px-3 py-3 transition-colors ${
      approved ? "border-emerald-500/20 bg-emerald-500/[0.06]" : "border-zinc-800 bg-[#101012] hover:border-zinc-700"
    }`} style={CARD_RENDER_STYLE}>
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950">
          <CircleDollarSign size={15} className={approved ? "text-emerald-200" : "text-zinc-400"} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h4 className="truncate text-sm font-semibold text-zinc-100">{metricTitle(metric)}</h4>
              <p className="mt-0.5 truncate text-[10px] text-zinc-600">{metricArea(metric)}</p>
            </div>
            <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] ${
              approved ? "border-emerald-500/25 text-emerald-200" : "border-zinc-700 text-zinc-500"
            }`}>
              {approved ? "Aprobada" : "Revision"}
            </span>
          </div>
          <p className="mt-3 line-clamp-3 min-h-12 text-xs leading-relaxed text-zinc-400">{metricDescription(metric)}</p>
          <div className="mt-3 flex items-center justify-between gap-3">
            <span className="line-clamp-1 rounded-full border border-zinc-800 px-2 py-0.5 text-[10px] text-zinc-600">
              {metricDefinition(metric)}
            </span>
            {!approved ? (
              <button
                type="button"
                onClick={onApprove}
                className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md bg-zinc-100 px-2.5 text-[11px] font-medium text-zinc-950 transition-colors hover:bg-white"
              >
                <Check size={12} />
                Aprobar
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </article>
  );
}

function DraftCard({
  draft,
  onApprove,
  onReject,
}: {
  draft: MetricDraft;
  onApprove: () => void;
  onReject: () => void;
}) {
  const approved = draft.status === "approved";
  const rejected = draft.status === "rejected";
  return (
    <article className={`rounded-lg border px-3 py-3 ${
      approved
        ? "border-emerald-500/20 bg-emerald-500/[0.06]"
        : rejected
          ? "border-zinc-800 bg-zinc-950/50 opacity-60"
          : "border-sky-500/20 bg-sky-500/[0.06]"
    }`} style={CARD_RENDER_STYLE}>
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950">
          <Sparkles size={15} className={approved ? "text-emerald-200" : "text-sky-200"} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h4 className="truncate text-sm font-semibold text-zinc-100">{businessText(draft.name, "Indicador sugerido")}</h4>
              <p className="mt-0.5 truncate text-[10px] text-zinc-600">Sugerencia</p>
            </div>
            <span className="shrink-0 rounded-full border border-zinc-700 px-2 py-0.5 text-[10px] text-zinc-500">
              {statusLabel(draft.status)}
            </span>
          </div>
          <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-zinc-400">
            {businessText(draft.description, "Indicador sugerido para revisar.")}
          </p>
          <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-zinc-500">
            {draftExplanation(draft)}
          </p>
          {draft.status === "draft" ? (
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={onApprove}
                className="inline-flex h-7 flex-1 items-center justify-center gap-1.5 rounded-md bg-zinc-100 px-2.5 text-[11px] font-medium text-zinc-950 transition-colors hover:bg-white"
              >
                <Check size={12} />
                Aprobar
              </button>
              <button
                type="button"
                onClick={onReject}
                className="inline-flex h-7 items-center justify-center rounded-md border border-zinc-800 px-2.5 text-[11px] font-medium text-zinc-500 transition-colors hover:bg-zinc-900 hover:text-zinc-300"
                aria-label="Rechazar"
              >
                <X size={12} />
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
}
