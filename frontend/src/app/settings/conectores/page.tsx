"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import {
  ArrowLeft,
  BarChart3,
  Check,
  ChevronRight,
  Database,
  FileSpreadsheet,
  KeyRound,
  Loader2,
  PlugZap,
  RefreshCw,
  Search,
  Sheet,
  ShieldCheck,
  Table2,
  Upload,
} from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { getSupabaseAuthHeaders } from "@/lib/supabase/auth";
import { SemanticOnboardingModal } from "@/components/semantic/SemanticOnboardingModal";

type ConnectorRow = {
  id: string;
  key: string;
  name: string;
  description: string;
  logo_path: string | null;
  section: string;
  status: "available" | "coming_soon" | "disabled";
  sort_order: number;
};

const fallbackConnectors: ConnectorRow[] = [
  {
    id: "powerbi",
    key: "powerbi",
    name: "Power BI",
    description: "Conecta modelos semanticos de Power BI con los flujos de Synthesis.",
    logo_path: "/connectors/powerbi.png",
    section: "essentials",
    status: "available",
    sort_order: 10,
  },
  {
    id: "excel",
    key: "excel",
    name: "Excel",
    description: "Importa, sincroniza y analiza archivos de Excel desde tus procesos operativos.",
    logo_path: "/connectors/excel.png",
    section: "essentials",
    status: "available",
    sort_order: 20,
  },
  {
    id: "google-sheets",
    key: "google-sheets",
    name: "Google Sheets",
    description: "Conecta hojas de calculo colaborativas para alimentar analisis y reportes.",
    logo_path: "/connectors/google-sheets.png",
    section: "essentials",
    status: "available",
    sort_order: 30,
  },
];

const fallbackIcons = {
  powerbi: BarChart3,
  excel: FileSpreadsheet,
  "google-sheets": Sheet,
};

const localLogoPaths = {
  powerbi: "/connectors/powerbi.png",
  excel: "/connectors/excel.png",
  "google-sheets": "/connectors/google-sheets.png",
};

const legacyBrandName = "Ny" + "ro";
const legacyAssistantName = `${legacyBrandName} AI`;

function withSynthesisBranding(connector: ConnectorRow): ConnectorRow {
  return {
    ...connector,
    description: connector.description
      .replace(/\b(?:BI AI|AI BI)\b/g, "Synthesis")
      .replaceAll(legacyAssistantName, "Synthesis")
      .replaceAll(legacyBrandName, "Synthesis"),
  };
}

const POWERBI_LOGO_PATH = "/connectors/powerbi.png";
const EXCEL_LOGO_PATH = "/connectors/excel.png";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type PowerBIDataset = {
  id: string;
  name: string;
  configured_by?: string;
  is_effective_identity_required?: boolean;
};

type PowerBIWorkspace = {
  id: string;
  name: string;
  datasets: PowerBIDataset[];
};

type PowerBIConnection = {
  id: string;
  name: string;
  status: string;
  is_default: boolean;
  config: {
    workspace_id?: string;
    workspace_name?: string;
    dataset_id?: string;
    dataset_name?: string;
  };
  last_sync_at?: string | null;
  last_error?: string | null;
};

type ExcelConnection = {
  id: string;
  name: string;
  status: string;
  is_default: boolean;
  config: {
    file_name?: string;
    engine?: string;
    tables?: Array<{
      sheet_name: string;
      table_name: string;
      rows: number;
      columns: number;
    }>;
  };
  last_sync_at?: string | null;
  last_error?: string | null;
};

type PowerBIAppConfig = {
  configured: boolean;
  source: "database" | "environment" | "missing";
  tenant_id: string;
  client_id: string;
  redirect_uri: string;
  default_redirect_uri: string;
  scopes: string[];
  secret_configured: boolean;
};

type PowerBIForm = {
  tenant_id: string;
  client_id: string;
  client_secret: string;
  redirect_uri: string;
};

async function readApiMessage(response: Response, fallback: string) {
  try {
    const contentType = response.headers.get("content-type") ?? "";
    const payload = contentType.includes("application/json") ? await response.json() : await response.text();

    if (typeof payload === "string") {
      return payload.trim().startsWith("{") ? fallback : payload || fallback;
    }

    const detail = payload?.detail;
    if (typeof payload?.message === "string") return payload.message;
    if (typeof detail?.message === "string") return detail.message;
    if (typeof detail === "string") return detail.trim().startsWith("{") ? fallback : detail;
  } catch {
    return fallback;
  }

  return fallback;
}

function cleanCallbackMessage(value: string | null) {
  if (!value) return "";
  return value.trim().startsWith("{") ? "" : value;
}

function formatLastSync(value?: string | null) {
  if (!value) return "";
  try {
    return new Intl.DateTimeFormat("es-AR", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export default function ConectoresSettingsPage() {
  const supabase = useMemo(() => createClient(), []);
  const [connectors, setConnectors] = useState<ConnectorRow[]>(fallbackConnectors.map(withSynthesisBranding));
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [selectedConnectorKey, setSelectedConnectorKey] = useState<"powerbi" | "excel" | null>(null);

  const [powerbiStatus, setPowerbiStatus] = useState("");
  const [powerbiConfig, setPowerbiConfig] = useState<PowerBIAppConfig | null>(null);
  const [powerbiForm, setPowerbiForm] = useState<PowerBIForm>({
    tenant_id: "common",
    client_id: "",
    client_secret: "",
    redirect_uri: "",
  });
  const [powerbiConnections, setPowerbiConnections] = useState<PowerBIConnection[]>([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState("");
  const [workspaces, setWorkspaces] = useState<PowerBIWorkspace[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [isPowerbiBusy, setIsPowerbiBusy] = useState(false);
  const [isWorkspaceLoading, setIsWorkspaceLoading] = useState(false);
  const [isConfigLoading, setIsConfigLoading] = useState(false);
  const [isConfigSaving, setIsConfigSaving] = useState(false);
  const [excelStatus, setExcelStatus] = useState("");
  const [excelConnections, setExcelConnections] = useState<ExcelConnection[]>([]);
  const [selectedExcelFile, setSelectedExcelFile] = useState<File | null>(null);
  const [isExcelBusy, setIsExcelBusy] = useState(false);
  const [semanticOnboardingConnectionId, setSemanticOnboardingConnectionId] = useState<string | null>(null);
  const [isSemanticOnboardingOpen, setIsSemanticOnboardingOpen] = useState(false);
  const completedOnboardingIdsRef = useRef<Set<string>>(new Set());

  const getAuthHeaders = async (): Promise<Record<string, string>> => {
    return (await getSupabaseAuthHeaders()).headers;
  };

  const persistActiveConnection = (connectionId: string, force = false) => {
    const current = window.localStorage.getItem("nyro_active_connection_id");
    if (force || !current) {
      window.localStorage.setItem("nyro_active_connection_id", connectionId);
    }
  };

  const applyPowerBIConfig = (appConfig: PowerBIAppConfig) => {
    setPowerbiForm({
      tenant_id: appConfig.tenant_id || "common",
      client_id: appConfig.client_id || "",
      client_secret: "",
      redirect_uri: appConfig.redirect_uri || appConfig.default_redirect_uri || "",
    });
  };

  const loadPowerBIConfig = async () => {
    setIsConfigLoading(true);
    try {
      const headers = await getAuthHeaders();
      if (!headers.Authorization) return null;
      const response = await fetch(`${apiBaseUrl}/connectors/powerbi/app-config`, { headers });
      if (!response.ok) {
        setPowerbiStatus(await readApiMessage(response, "No pude cargar la configuracion de Power BI."));
        return null;
      }
      const data = await response.json();
      const appConfig = data.app_config as PowerBIAppConfig;
      setPowerbiConfig(appConfig);
      applyPowerBIConfig(appConfig);
      return appConfig;
    } catch {
      setPowerbiStatus("No pude cargar la configuracion de Power BI.");
      return null;
    } finally {
      setIsConfigLoading(false);
    }
  };

  const loadPowerBIConnections = async () => {
    try {
      const headers = await getAuthHeaders();
      if (!headers.Authorization) return;
      const response = await fetch(`${apiBaseUrl}/connectors/powerbi/connections`, { headers });
      if (!response.ok) {
        setPowerbiStatus(await readApiMessage(response, "No pude cargar conexiones de Power BI."));
        return;
      }
      const data = await response.json();
      const rows = (data.connections ?? []) as PowerBIConnection[];
      setPowerbiConnections(rows);
      const active = rows.find((row) => row.is_default) ?? rows[0];
      if (active) {
        setSelectedConnectionId(active.id);
        persistActiveConnection(active.id);
      }
    } catch {
      setPowerbiStatus("No pude cargar conexiones de Power BI.");
    }
  };

  const loadExcelConnections = async () => {
    try {
      const headers = await getAuthHeaders();
      if (!headers.Authorization) return;
      const response = await fetch(`${apiBaseUrl}/connectors/excel/connections`, { headers });
      if (!response.ok) {
        setExcelStatus(await readApiMessage(response, "No pude cargar conexiones de Excel."));
        return;
      }
      const data = await response.json();
      const rows = ((data.connections ?? []) as ExcelConnection[]).filter((connection) =>
        ["review", "ready", "connected"].includes(connection.status),
      );
      setExcelConnections(rows);
      const reviewConnection = rows.find((row) => row.status === "review");
      const active = reviewConnection ?? rows.find((row) => row.is_default) ?? rows[0];
      if (active) {
        persistActiveConnection(active.id, active.status === "review");
      }
      if (reviewConnection && !completedOnboardingIdsRef.current.has(reviewConnection.id)) {
        setSelectedConnectorKey("excel");
        setSemanticOnboardingConnectionId(reviewConnection.id);
        setIsSemanticOnboardingOpen(true);
      }
    } catch {
      setExcelStatus("No pude cargar conexiones de Excel.");
    }
  };

  useEffect(() => {
    let cancelled = false;

    const fetchConnectors = async () => {
      const { data, error } = await supabase
        .from("connectors")
        .select("id, key, name, description, logo_path, section, status, sort_order")
        .eq("section", "essentials")
        .order("sort_order", { ascending: true });

      if (cancelled) return;

      if (!error && data?.length) {
        setConnectors((data as ConnectorRow[]).map(withSynthesisBranding));
      }

      setIsLoading(false);
    };

    void fetchConnectors();

    return () => {
      cancelled = true;
    };
  }, [supabase]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadPowerBIConnections();
      void loadExcelConnections();
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const openPowerBIDetail = () => {
    setSelectedConnectorKey("powerbi");
    setPowerbiStatus("");
    void loadPowerBIConfig();
    void loadPowerBIConnections();
  };

  const openExcelDetail = () => {
    setSelectedConnectorKey("excel");
    setExcelStatus("");
    void loadExcelConnections();
  };

  const uploadExcelWorkbook = async (fileOverride?: File | null) => {
    const workbookFile = fileOverride ?? selectedExcelFile;
    if (!workbookFile) {
      setExcelStatus("Selecciona un workbook .xlsx.");
      return;
    }
    setIsExcelBusy(true);
    setExcelStatus("Subiendo workbook...");
    try {
      const headers = await getAuthHeaders();
      if (!headers.Authorization) {
        setExcelStatus("Necesitas iniciar sesion para conectar Excel.");
        return;
      }
      const response = await fetch(`${apiBaseUrl}/connectors/excel/upload`, {
        method: "POST",
        headers: {
          ...headers,
          "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "X-File-Name": encodeURIComponent(workbookFile.name),
        },
        body: await workbookFile.arrayBuffer(),
      });
      if (!response.ok) {
        const fallback = "No pude procesar el workbook Excel.";
        const errorPayload = await response.json().catch(() => null);
        if (response.status === 409 && errorPayload?.detail?.code === "company_context_required") {
          setSemanticOnboardingConnectionId(null);
          setIsSemanticOnboardingOpen(true);
          setExcelStatus(errorPayload.detail.message || "Completa el contexto de empresa para continuar.");
          return;
        }
        const detail = errorPayload?.detail;
        setExcelStatus(
          errorPayload?.message ||
            detail?.message ||
            (typeof detail === "string" ? detail : "") ||
            fallback,
        );
        return;
      }
      const data = await response.json();
      const connection = data.connection as ExcelConnection | undefined;
      const onboardingConnectionId =
        connection?.id ||
        (typeof data.onboarding?.connection_id === "string" ? data.onboarding.connection_id : undefined) ||
        (typeof data.connection_id === "string" ? data.connection_id : undefined);
      setSelectedConnectorKey("excel");
      setSemanticOnboardingConnectionId(onboardingConnectionId ?? null);
      setIsSemanticOnboardingOpen(true);
      if (onboardingConnectionId) {
        completedOnboardingIdsRef.current.delete(onboardingConnectionId);
        persistActiveConnection(onboardingConnectionId, true);
        setSelectedExcelFile(null);
      }
      setExcelStatus("Workbook procesado. Revisemos el diccionario semantico.");
      void loadExcelConnections();
    } catch {
      setExcelStatus("No pude subir o procesar el workbook Excel.");
    } finally {
      setIsExcelBusy(false);
    }
  };

  const savePowerBIConfig = async () => {
    setIsConfigSaving(true);
    setPowerbiStatus("");
    try {
      const headers = await getAuthHeaders();
      if (!headers.Authorization) {
        setPowerbiStatus("Necesitas iniciar sesion para configurar Power BI.");
        return;
      }
      const response = await fetch(`${apiBaseUrl}/connectors/powerbi/app-config`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify(powerbiForm),
      });
      if (!response.ok) {
        setPowerbiStatus(await readApiMessage(response, "Completa la configuracion de Microsoft Entra."));
        return;
      }
      const data = await response.json();
      const appConfig = data.app_config as PowerBIAppConfig;
      setPowerbiConfig(appConfig);
      applyPowerBIConfig(appConfig);
      setPowerbiStatus("Configuracion guardada. Ya podes conectar la cuenta Microsoft.");
    } catch {
      setPowerbiStatus("No pude guardar la configuracion de Power BI.");
    } finally {
      setIsConfigSaving(false);
    }
  };

  const startPowerBIAuth = async () => {
    setIsPowerbiBusy(true);
    setPowerbiStatus("");
    try {
      const headers = await getAuthHeaders();
      if (!headers.Authorization) {
        setPowerbiStatus("Necesitas iniciar sesion para conectar Power BI.");
        return;
      }
      if (!powerbiConfig?.configured) {
        setPowerbiStatus("Guarda la configuracion de Microsoft Entra antes de conectar la cuenta.");
        return;
      }
      const response = await fetch(`${apiBaseUrl}/connectors/powerbi/start-auth`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ redirect_path: "/settings/conectores" }),
      });
      if (!response.ok) {
        setPowerbiStatus(await readApiMessage(response, "No pude iniciar la conexion con Microsoft."));
        return;
      }
      const data = await response.json();
      window.location.href = data.auth_url;
    } catch {
      setPowerbiStatus("No pude iniciar la conexion con Microsoft.");
    } finally {
      setIsPowerbiBusy(false);
    }
  };

  const loadPowerBIWorkspaces = async (connectionId = selectedConnectionId) => {
    if (!connectionId) {
      setPowerbiStatus("Primero conecta tu cuenta Microsoft.");
      return;
    }
    setIsWorkspaceLoading(true);
    setPowerbiStatus("");
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(
        `${apiBaseUrl}/connectors/powerbi/workspaces?connection_id=${encodeURIComponent(connectionId)}`,
        { headers },
      );
      if (!response.ok) {
        setPowerbiStatus(await readApiMessage(response, "No pude listar workspaces de Power BI."));
        return;
      }
      const data = await response.json();
      const rows = (data.workspaces ?? []) as PowerBIWorkspace[];
      setWorkspaces(rows);
      if (!rows.length) {
        setPowerbiStatus("No encontre workspaces disponibles para esta cuenta.");
      }
    } catch {
      setPowerbiStatus("No pude listar workspaces de Power BI.");
    } finally {
      setIsWorkspaceLoading(false);
    }
  };

  const connectPowerBIModel = async () => {
    const workspace = workspaces.find((item) => item.id === selectedWorkspaceId);
    const dataset = workspace?.datasets.find((item) => item.id === selectedDatasetId);
    if (!workspace || !dataset || !selectedConnectionId) return;
    setIsPowerbiBusy(true);
    setPowerbiStatus("");
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/connectors/powerbi/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({
          connection_id: selectedConnectionId,
          workspace_id: workspace.id,
          workspace_name: workspace.name,
          dataset_id: dataset.id,
          dataset_name: dataset.name,
          sync_now: true,
        }),
      });
      if (!response.ok) {
        setPowerbiStatus(await readApiMessage(response, "No pude conectar el modelo seleccionado."));
        return;
      }
      persistActiveConnection(selectedConnectionId, true);
      setPowerbiStatus("Modelo conectado. La sincronizacion de metadata quedo en proceso.");
      void loadPowerBIConnections();
    } catch {
      setPowerbiStatus("No pude conectar el modelo seleccionado.");
    } finally {
      setIsPowerbiBusy(false);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams(window.location.search);
      const callbackStatus = params.get("powerbi");
      const connectionId = params.get("connection_id");
      const excelOnboardingId = params.get("excel_onboarding");
      const message = cleanCallbackMessage(params.get("message"));

      if (excelOnboardingId) {
        completedOnboardingIdsRef.current.delete(excelOnboardingId);
        setSelectedConnectorKey("excel");
        setSemanticOnboardingConnectionId(excelOnboardingId);
        setIsSemanticOnboardingOpen(true);
        void loadExcelConnections();
        window.history.replaceState(null, "", "/settings/conectores");
        return;
      }

      if (!callbackStatus) return;

      setSelectedConnectorKey("powerbi");
      void loadPowerBIConfig();

      if (callbackStatus === "connected" && connectionId) {
        setSelectedConnectionId(connectionId);
        persistActiveConnection(connectionId, true);
        setPowerbiStatus("Cuenta Microsoft conectada. Elegi el workspace y el modelo semantico.");
        void loadPowerBIConnections();
        void loadPowerBIWorkspaces(connectionId);
      }

      if (callbackStatus === "error") {
        setPowerbiStatus(message || "No pude completar la conexion con Power BI.");
      }

      window.history.replaceState(null, "", "/settings/conectores");
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const filteredConnectors = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return connectors;

    return connectors.filter((connector) =>
      [connector.name, connector.description].some((value) => value.toLowerCase().includes(query)),
    );
  }, [connectors, search]);

  const connectedPowerBI = powerbiConnections.find((connection) => connection.is_default) ?? powerbiConnections[0];
  const connectedExcel =
    excelConnections.find((connection) => connection.status === "review") ??
    excelConnections.find((connection) => connection.is_default) ??
    excelConnections[0];

  return (
    <>
      <section className="flex-1 overflow-y-auto bg-[#0a0a0b]">
        {selectedConnectorKey === "excel" ? (
          <ExcelIntegrationDetail
            status={excelStatus}
            connections={excelConnections}
            selectedFile={selectedExcelFile}
            isBusy={isExcelBusy}
            onBack={() => setSelectedConnectorKey(null)}
            onFileChange={(file) => {
              setSelectedExcelFile(file);
              if (file) void uploadExcelWorkbook(file);
            }}
            onUpload={uploadExcelWorkbook}
            onOpenOnboarding={(connectionId) => {
              completedOnboardingIdsRef.current.delete(connectionId);
              setSemanticOnboardingConnectionId(connectionId);
              setIsSemanticOnboardingOpen(true);
            }}
          />
        ) : selectedConnectorKey === "powerbi" ? (
          <PowerBIIntegrationDetail
            appConfig={powerbiConfig}
            form={powerbiForm}
            onFormChange={(field, value) => setPowerbiForm((current) => ({ ...current, [field]: value }))}
            status={powerbiStatus}
            connections={powerbiConnections}
            workspaces={workspaces}
            selectedConnectionId={selectedConnectionId}
            selectedWorkspaceId={selectedWorkspaceId}
            selectedDatasetId={selectedDatasetId}
            isBusy={isPowerbiBusy}
            isConfigLoading={isConfigLoading}
            isConfigSaving={isConfigSaving}
            isWorkspaceLoading={isWorkspaceLoading}
            onBack={() => setSelectedConnectorKey(null)}
            onSaveConfig={savePowerBIConfig}
            onStartAuth={startPowerBIAuth}
            onLoadWorkspaces={() => loadPowerBIWorkspaces()}
            onConnectionChange={(id) => {
              setSelectedConnectionId(id);
              setSelectedWorkspaceId("");
              setSelectedDatasetId("");
              persistActiveConnection(id, true);
              void loadPowerBIWorkspaces(id);
            }}
            onWorkspaceChange={(id) => {
              setSelectedWorkspaceId(id);
              setSelectedDatasetId("");
            }}
            onDatasetChange={setSelectedDatasetId}
            onConnect={connectPowerBIModel}
          />
        ) : (
          <div className="mx-auto w-full max-w-[760px] px-5 py-10 md:py-16">
            <header className="mb-11">
              <h1 className="text-2xl font-semibold text-zinc-50">Conectores</h1>
              <p className="mt-2 text-sm text-zinc-500">
                Conecta Synthesis con tus fuentes de datos, planillas y herramientas de BI.
              </p>

              <div className="mt-12 flex h-11 items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/45 px-4 text-zinc-500 transition-colors focus-within:border-zinc-700">
                <Search size={17} />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Buscar conectores"
                  className="h-full min-w-0 flex-1 bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
                />
              </div>
            </header>

            <section>
              <h2 className="mb-4 text-xs font-semibold uppercase tracking-wide text-zinc-500">Esenciales</h2>

              <div className="grid gap-4 md:grid-cols-3">
                {filteredConnectors.map((connector) => (
                  <ConnectorCard
                    key={connector.id}
                    connector={connector}
                    statusLabel={
                      connector.key === "powerbi" && connectedPowerBI
                        ? "Conectado"
                        : connector.key === "excel" && connectedExcel
                          ? connectedExcel.status === "review"
                            ? "En revision"
                            : "Conectado"
                          : undefined
                    }
                    onSelect={
                      connector.key === "powerbi"
                        ? openPowerBIDetail
                        : connector.key === "excel"
                          ? openExcelDetail
                          : undefined
                    }
                  />
                ))}
              </div>

              {!isLoading && filteredConnectors.length === 0 && (
                <div className="rounded-lg border border-zinc-800 bg-zinc-900/45 px-4 py-8 text-center text-sm text-zinc-500">
                  No se encontraron conectores.
                </div>
              )}
            </section>
          </div>
        )}
      </section>
      <SemanticOnboardingModal
        isOpen={isSemanticOnboardingOpen}
        connectionId={semanticOnboardingConnectionId}
        selectedFile={selectedExcelFile}
        onClose={() => setIsSemanticOnboardingOpen(false)}
        onRetryUpload={uploadExcelWorkbook}
        onCompleted={(connectionId) => {
          completedOnboardingIdsRef.current.add(connectionId);
          persistActiveConnection(connectionId, true);
          setIsSemanticOnboardingOpen(false);
          setSemanticOnboardingConnectionId(null);
          setExcelStatus("Catalogo semantico publicado.");
          void loadExcelConnections();
        }}
      />
    </>
  );
}

function ConnectorCard({
  connector,
  statusLabel,
  onSelect,
}: {
  connector: ConnectorRow;
  statusLabel?: string;
  onSelect?: () => void;
}) {
  const [logoFailed, setLogoFailed] = useState(false);
  const FallbackIcon = fallbackIcons[connector.key as keyof typeof fallbackIcons] ?? FileSpreadsheet;
  const logoPath = localLogoPaths[connector.key as keyof typeof localLogoPaths] ?? connector.logo_path;
  const showLogo = logoPath && !logoFailed;

  return (
    <article
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (onSelect && (event.key === "Enter" || event.key === " ")) onSelect();
      }}
      className="min-h-[156px] rounded-lg border border-zinc-800 bg-zinc-950/30 px-5 py-4 transition-colors hover:border-zinc-700 hover:bg-zinc-900/40"
    >
      <div className="mb-4 flex items-center gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-md bg-white text-zinc-950">
          {showLogo ? (
            <Image
              src={logoPath}
              alt=""
              width={24}
              height={24}
              className="h-6 w-6 object-contain"
              onError={() => setLogoFailed(true)}
            />
          ) : (
            <FallbackIcon size={20} strokeWidth={2.2} />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-zinc-50">{connector.name}</h3>
          {statusLabel ? (
            <span className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-emerald-300">
              <Check size={12} />
              {statusLabel}
            </span>
          ) : null}
        </div>
      </div>

      <p className="line-clamp-4 text-sm leading-snug text-zinc-400">{connector.description}</p>
    </article>
  );
}

function ExcelIntegrationDetail({
  status,
  connections,
  selectedFile,
  isBusy,
  onBack,
  onFileChange,
  onUpload,
  onOpenOnboarding,
}: {
  status: string;
  connections: ExcelConnection[];
  selectedFile: File | null;
  isBusy: boolean;
  onBack: () => void;
  onFileChange: (file: File | null) => void;
  onUpload: () => void;
  onOpenOnboarding: (connectionId: string) => void;
}) {
  const readyConnections = connections.filter((connection) => ["review", "ready", "connected"].includes(connection.status));
  const activeConnection =
    readyConnections.find((connection) => connection.status === "review") ??
    readyConnections.find((connection) => connection.is_default) ??
    readyConnections[0];
  const tables = activeConnection?.config?.tables ?? [];
  const workbookName = activeConnection?.config?.file_name || activeConnection?.name || "Sin workbook conectado";
  const isInReview = activeConnection?.status === "review";

  return (
    <div className="mx-auto w-full max-w-[680px] px-5 py-8 md:py-12">
      <button
        type="button"
        onClick={onBack}
        className="mb-10 inline-flex h-8 items-center gap-2 rounded-md px-1 text-sm text-zinc-500 transition-colors hover:text-zinc-200"
      >
        <ArrowLeft size={16} />
        Conectores
      </button>

      <header className="mb-6 flex items-center gap-4">
        <span className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-white">
          <Image src={EXCEL_LOGO_PATH} alt="" width={36} height={36} className="h-9 w-9 object-contain" priority />
        </span>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-zinc-50">Excel</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Convierte workbooks multi-hoja en un modelo semantico consultable por Synthesis.
          </p>
        </div>
      </header>

      <section className="rounded-lg border border-zinc-800 bg-zinc-950/35 p-4">
        <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="grid grid-cols-2 gap-8">
            <MetaLabel label="BUILT BY" value="Synthesis" />
            <MetaLabel label="ENGINE" value="DuckDB + Cube" />
          </div>
          <label
            className={`inline-flex h-9 items-center justify-center gap-2 rounded-full bg-[#217346] px-4 text-xs font-semibold text-white transition-colors hover:bg-[#2b8a56] ${
              isBusy ? "pointer-events-none opacity-70" : "cursor-pointer"
            }`}
          >
            {isBusy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
            {isBusy ? "Procesando" : "Seleccionar XLSX"}
            <input
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              disabled={isBusy}
              className="sr-only"
              onChange={(event) => {
                onFileChange(event.target.files?.[0] ?? null);
                event.currentTarget.value = "";
              }}
            />
          </label>
        </div>

        <ExcelPreview />

        <div className="mt-6">
          <h2 className="text-sm font-semibold text-zinc-50">Overview</h2>
          <p className="mt-2 text-sm leading-relaxed text-zinc-400">
            DuckDB perfila el workbook y Cube queda como capa de ejecucion semantica. Las hojas `Fact_*`
            generan metricas base y las hojas `Dim_*` contextualizan dimensiones y relaciones.
          </p>
        </div>
      </section>

      <section className="mt-6 rounded-lg border border-zinc-800 bg-zinc-950/35 p-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-zinc-50">
              {activeConnection ? (isInReview ? "Workbook Excel en revision" : "Workbook Excel conectado") : "Workbook Excel no conectado"}
            </h2>
            <p className="mt-1 truncate text-xs text-zinc-500">{selectedFile?.name || workbookName}</p>
          </div>
          <button
            type="button"
            onClick={onUpload}
            disabled={isBusy || !selectedFile}
            className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-md bg-zinc-100 px-3 text-xs font-medium text-zinc-950 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isBusy ? <Loader2 size={14} className="animate-spin" /> : <Table2 size={14} />}
            Procesar workbook
          </button>
          {isInReview && activeConnection ? (
            <button
              type="button"
              onClick={() => onOpenOnboarding(activeConnection.id)}
              className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-md border border-emerald-500/25 bg-emerald-500/10 px-3 text-xs font-medium text-emerald-200 transition-colors hover:border-emerald-400/40 hover:bg-emerald-500/15"
            >
              <ShieldCheck size={14} />
              Continuar onboarding
            </button>
          ) : null}
        </div>

        {status ? <div className="mt-4 text-xs text-zinc-400">{status}</div> : null}

        {tables.length > 0 ? (
          <div className="mt-4 divide-y divide-zinc-800 overflow-hidden rounded-md border border-zinc-800">
            {tables.slice(0, 6).map((table) => (
              <div key={`${table.sheet_name}-${table.table_name}`} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 px-3 py-2">
                <div className="min-w-0">
                  <div className="truncate text-xs font-medium text-zinc-200">{table.sheet_name}</div>
                  <div className="truncate text-[11px] text-zinc-500">{table.table_name}</div>
                </div>
                <div className="text-right text-[11px] text-zinc-500">
                  {table.rows} filas / {table.columns} cols
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-4 rounded-md border border-dashed border-zinc-800 px-3 py-4 text-xs leading-relaxed text-zinc-500">
            El workbook debe tener headers en la primera fila util. Las hojas pueden llamarse `Dim_Clientes`,
            `Fact_Ventas`, `Dim_Productos` y similares.
          </div>
        )}
      </section>
    </div>
  );
}

function PowerBIIntegrationDetail({
  appConfig,
  form,
  onFormChange,
  status,
  connections,
  workspaces,
  selectedConnectionId,
  selectedWorkspaceId,
  selectedDatasetId,
  isBusy,
  isConfigLoading,
  isConfigSaving,
  isWorkspaceLoading,
  onBack,
  onSaveConfig,
  onStartAuth,
  onLoadWorkspaces,
  onConnectionChange,
  onWorkspaceChange,
  onDatasetChange,
  onConnect,
}: {
  appConfig: PowerBIAppConfig | null;
  form: PowerBIForm;
  onFormChange: (field: keyof PowerBIForm, value: string) => void;
  status: string;
  connections: PowerBIConnection[];
  workspaces: PowerBIWorkspace[];
  selectedConnectionId: string;
  selectedWorkspaceId: string;
  selectedDatasetId: string;
  isBusy: boolean;
  isConfigLoading: boolean;
  isConfigSaving: boolean;
  isWorkspaceLoading: boolean;
  onBack: () => void;
  onSaveConfig: () => void;
  onStartAuth: () => void;
  onLoadWorkspaces: () => void;
  onConnectionChange: (id: string) => void;
  onWorkspaceChange: (id: string) => void;
  onDatasetChange: (id: string) => void;
  onConnect: () => void;
}) {
  const selectedWorkspace = workspaces.find((workspace) => workspace.id === selectedWorkspaceId);
  const selectedConnection = connections.find((connection) => connection.id === selectedConnectionId);
  const canConnectModel = Boolean(selectedConnectionId && selectedWorkspaceId && selectedDatasetId);
  const isConfigured = Boolean(appConfig?.configured);
  const accountTitle = selectedConnection ? "Cuenta Power BI conectada" : "Cuenta Power BI no conectada";
  const modelTitle = selectedConnection?.config?.dataset_name || selectedConnection?.name || "Sin modelo seleccionado";
  const sourceLabel =
    appConfig?.source === "environment"
      ? "Fallback de entorno"
      : appConfig?.configured
        ? "Configuracion guardada"
        : isConfigLoading
          ? "Cargando"
          : "Pendiente";

  return (
    <div className="mx-auto w-full max-w-[680px] px-5 py-8 md:py-12">
      <button
        type="button"
        onClick={onBack}
        className="mb-10 inline-flex h-8 items-center gap-2 rounded-md px-1 text-sm text-zinc-500 transition-colors hover:text-zinc-200"
      >
        <ArrowLeft size={16} />
        Conectores
      </button>

      <header className="mb-6 flex items-center gap-4">
        <span className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-white">
          <Image src={POWERBI_LOGO_PATH} alt="" width={36} height={36} className="h-9 w-9 object-contain" priority />
        </span>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-zinc-50">Power BI</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Consulta semantic models en vivo y conserva el contexto de negocio para la IA.
          </p>
        </div>
      </header>

      <section className="rounded-lg border border-zinc-800 bg-zinc-950/35 p-4">
        <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="grid grid-cols-2 gap-8">
            <MetaLabel label="BUILT BY" value="Synthesis" />
            <MetaLabel label="PROVIDER" value="Microsoft" />
          </div>
          <button
            type="button"
            onClick={isConfigured ? onStartAuth : onSaveConfig}
            disabled={isBusy || isConfigSaving}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-full bg-[#f2c811] px-4 text-xs font-semibold text-zinc-950 transition-colors hover:bg-[#ffd633] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isBusy || isConfigSaving ? <Loader2 size={14} className="animate-spin" /> : <PlugZap size={14} />}
            {isConfigured ? "Conectar" : "Guardar config"}
          </button>
        </div>

        <PowerBIPreview />

        <div className="mt-6">
          <h2 className="text-sm font-semibold text-zinc-50">Overview</h2>
          <p className="mt-2 text-sm leading-relaxed text-zinc-400">
            Power BI queda como provider semantico vivo: Synthesis sincroniza metadata, entiende tablas,
            columnas, medidas y relaciones, y ejecuta consultas DAX de lectura sobre el modelo elegido.
          </p>
        </div>
      </section>

      <section className="mt-6 rounded-lg border border-zinc-800 bg-zinc-950/35 p-4">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <KeyRound size={16} className="text-zinc-400" />
            <h2 className="text-sm font-semibold text-zinc-100">Aplicacion Microsoft Entra</h2>
          </div>
          <span className="rounded-md border border-zinc-800 px-2 py-1 text-[11px] font-medium text-zinc-400">
            {sourceLabel}
          </span>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <label className="grid gap-1.5">
            <span className="text-[11px] font-medium text-zinc-500">Tenant ID</span>
            <input
              value={form.tenant_id}
              onChange={(event) => onFormChange("tenant_id", event.target.value)}
              placeholder="common"
              className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-100 outline-none focus:border-zinc-700"
            />
          </label>

          <label className="grid gap-1.5">
            <span className="text-[11px] font-medium text-zinc-500">Client ID</span>
            <input
              value={form.client_id}
              onChange={(event) => onFormChange("client_id", event.target.value)}
              placeholder="Application client id"
              className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-100 outline-none focus:border-zinc-700"
            />
          </label>

          <label className="grid gap-1.5">
            <span className="text-[11px] font-medium text-zinc-500">Client Secret</span>
            <input
              value={form.client_secret}
              onChange={(event) => onFormChange("client_secret", event.target.value)}
              type="password"
              placeholder={appConfig?.secret_configured ? "Ya configurado; escribir para reemplazar" : "Client secret"}
              className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-100 outline-none focus:border-zinc-700"
            />
          </label>

          <label className="grid gap-1.5">
            <span className="text-[11px] font-medium text-zinc-500">Redirect URI</span>
            <input
              value={form.redirect_uri}
              onChange={(event) => onFormChange("redirect_uri", event.target.value)}
              placeholder={appConfig?.default_redirect_uri ?? "http://localhost:8000/connectors/powerbi/callback"}
              className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-100 outline-none focus:border-zinc-700"
            />
          </label>
        </div>

        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs leading-relaxed text-zinc-500">
            Redirect URI registrada en Microsoft Entra. Client Secret cifrado server-side.
          </p>
          <button
            type="button"
            onClick={onSaveConfig}
            disabled={isConfigSaving}
            className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-md bg-zinc-100 px-3 text-xs font-medium text-zinc-950 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isConfigSaving ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
            Guardar
          </button>
        </div>
      </section>

      <section className="mt-6 rounded-lg border border-zinc-800 bg-zinc-950/35 p-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-zinc-50">{accountTitle}</h2>
            <p className="mt-1 truncate text-xs text-zinc-500">{modelTitle}</p>
          </div>
          <button
            type="button"
            onClick={onStartAuth}
            disabled={isBusy || !isConfigured}
            className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-md border border-zinc-800 px-3 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-900 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isBusy ? <Loader2 size={14} className="animate-spin" /> : <PlugZap size={14} />}
            Connected accounts
            <ChevronRight size={14} />
          </button>
        </div>

        {connections.length > 0 ? (
          <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
            <label className="grid gap-1.5">
              <span className="text-[11px] font-medium text-zinc-500">Conexion</span>
              <select
                value={selectedConnectionId}
                onChange={(event) => onConnectionChange(event.target.value)}
                className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-200 outline-none focus:border-zinc-700"
              >
                {connections.map((connection) => (
                  <option key={connection.id} value={connection.id}>
                    {connection.name || "Power BI"} - {connection.status}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={onLoadWorkspaces}
              disabled={!selectedConnectionId || isWorkspaceLoading}
              className="mt-auto inline-flex h-9 items-center justify-center gap-2 rounded-md border border-zinc-800 px-3 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-900 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isWorkspaceLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              Workspaces
            </button>
          </div>
        ) : null}

        {workspaces.length > 0 ? (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <label className="grid gap-1.5">
              <span className="text-[11px] font-medium text-zinc-500">Workspace</span>
              <select
                value={selectedWorkspaceId}
                onChange={(event) => onWorkspaceChange(event.target.value)}
                className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-200 outline-none focus:border-zinc-700"
              >
                <option value="">Seleccionar workspace</option>
                {workspaces.map((workspace) => (
                  <option key={workspace.id} value={workspace.id}>
                    {workspace.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="grid gap-1.5">
              <span className="text-[11px] font-medium text-zinc-500">Semantic model</span>
              <select
                value={selectedDatasetId}
                onChange={(event) => onDatasetChange(event.target.value)}
                className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-200 outline-none focus:border-zinc-700"
                disabled={!selectedWorkspace}
              >
                <option value="">Seleccionar modelo</option>
                {(selectedWorkspace?.datasets ?? []).map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
        ) : null}

        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-h-5 text-xs text-zinc-500">
            {status ? (
              status
            ) : selectedConnection?.last_sync_at ? (
              <span className="inline-flex items-center gap-2 text-emerald-300">
                <Check size={13} />
                Metadata sincronizada {formatLastSync(selectedConnection.last_sync_at)}
              </span>
            ) : selectedConnection?.last_error ? (
              <span className="text-amber-300">{selectedConnection.last_error}</span>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onConnect}
            disabled={!canConnectModel || isBusy}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-zinc-100 px-3 text-xs font-medium text-zinc-950 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isBusy ? <Loader2 size={14} className="animate-spin" /> : <Database size={14} />}
            Usar modelo
          </button>
        </div>
      </section>
    </div>
  );
}

function MetaLabel({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{label}</div>
      <div className="mt-1 text-xs font-semibold text-zinc-100">{value}</div>
    </div>
  );
}

function ExcelPreview() {
  return (
    <div className="grid gap-2 md:grid-cols-2">
      <div className="relative h-44 overflow-hidden rounded-md bg-[#217346]">
        <Image
          src={EXCEL_LOGO_PATH}
          alt=""
          width={150}
          height={150}
          className="absolute -bottom-12 -right-8 h-36 w-36 object-contain opacity-25"
        />
        <div className="absolute left-5 top-5 w-44 rounded-md border border-black/10 bg-white p-3 shadow-xl">
          <div className="mb-2 grid grid-cols-3 gap-1">
            <span className="h-3 rounded-sm bg-[#217346]" />
            <span className="h-3 rounded-sm bg-zinc-200" />
            <span className="h-3 rounded-sm bg-zinc-200" />
          </div>
          <div className="space-y-1">
            {Array.from({ length: 5 }).map((_, row) => (
              <div key={row} className="grid grid-cols-3 gap-1">
                <span className="h-2 rounded-sm bg-zinc-200" />
                <span className="h-2 rounded-sm bg-zinc-100" />
                <span className="h-2 rounded-sm bg-zinc-100" />
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="relative h-44 overflow-hidden rounded-md bg-zinc-100">
        <div className="absolute -right-10 top-7 size-32 rounded-full bg-[#217346]/80" />
        <div className="absolute left-6 top-8 w-44 rounded-md border border-zinc-200 bg-white p-3 shadow-xl">
          <div className="mb-2 flex items-center gap-2">
            <span className="size-5 overflow-hidden rounded bg-white">
              <Image src={EXCEL_LOGO_PATH} alt="" width={20} height={20} className="h-5 w-5 object-contain" />
            </span>
            <span className="h-2 w-24 rounded-full bg-zinc-300" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <span className="rounded-sm bg-[#dff3e6] px-2 py-3 text-[10px] font-semibold text-[#217346]">Dim</span>
            <span className="rounded-sm bg-[#dff3e6] px-2 py-3 text-[10px] font-semibold text-[#217346]">Fact</span>
          </div>
          <div className="mt-3 h-2 w-32 rounded-full bg-zinc-200" />
          <div className="mt-2 h-2 w-24 rounded-full bg-zinc-200" />
        </div>
      </div>
    </div>
  );
}

function PowerBIPreview() {
  return (
    <div className="grid gap-2 md:grid-cols-2">
      <div className="relative h-44 overflow-hidden rounded-md bg-[#f2c811]">
        <Image
          src={POWERBI_LOGO_PATH}
          alt=""
          width={160}
          height={160}
          className="absolute -bottom-14 -right-10 h-40 w-40 object-contain opacity-25"
        />
        <div className="absolute left-5 top-5 w-40 rounded-md border border-black/10 bg-white/90 p-3 shadow-xl">
          <div className="mb-2 h-2 w-20 rounded-full bg-zinc-300" />
          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-3">
              <span className="h-2 w-12 rounded-full bg-zinc-200" />
              <span className="h-2 w-8 rounded-full bg-[#d99b00]" />
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="h-2 w-16 rounded-full bg-zinc-200" />
              <span className="h-2 w-10 rounded-full bg-[#d99b00]" />
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="h-2 w-10 rounded-full bg-zinc-200" />
              <span className="h-2 w-7 rounded-full bg-[#d99b00]" />
            </div>
          </div>
        </div>
      </div>

      <div className="relative h-44 overflow-hidden rounded-md bg-zinc-100">
        <div className="absolute -right-12 top-6 size-36 rounded-full bg-[#f2c811]/80" />
        <div className="absolute left-6 top-8 w-44 rounded-md border border-zinc-200 bg-white p-3 shadow-xl">
          <div className="mb-2 flex items-center gap-2">
            <span className="size-5 overflow-hidden rounded bg-white">
              <Image src={POWERBI_LOGO_PATH} alt="" width={20} height={20} className="h-5 w-5 object-contain" />
            </span>
            <span className="h-2 w-24 rounded-full bg-zinc-300" />
          </div>
          <div className="space-y-2">
            <div className="h-2 w-32 rounded-full bg-zinc-200" />
            <div className="h-2 w-24 rounded-full bg-zinc-200" />
            <div className="grid grid-cols-3 gap-1 pt-2">
              <span className="h-8 rounded-sm bg-[#f2c811]" />
              <span className="h-8 rounded-sm bg-[#e0a000]" />
              <span className="h-8 rounded-sm bg-[#b87500]" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
