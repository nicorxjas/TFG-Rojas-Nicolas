"use client";

import { useState, useEffect, useCallback } from 'react';
import InformesSidebar from '@/components/informes/InformesSidebar';
import InformesFeed from '@/components/informes/InformesFeed';
import InformesReader from '@/components/informes/InformesReader';
import { createClient } from '@/lib/supabase/client';
import { getSupabaseAuthHeaders } from '@/lib/supabase/auth';
import { Report } from '@/types/informes';
import CreateReportModal from '@/components/informes/CreateReportModal';
import { CheckCircle2, FilePlus2 } from 'lucide-react';

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const reportSelect = '*, report_agents(agents(*))';

type AgentSummary = {
  id: string;
  name: string;
  description?: string;
  systemPrompt?: string;
  category?: string;
  iconType?: "icon" | "emoji";
  iconName?: string;
  iconColor?: string;
  iconEmoji?: string;
  createdAt?: string;
};

type ReportRow = Report & {
  id: string;
};

type CreateReportPayload = {
  template_id: string | null;
  name: string;
  prompt: string;
  include_charts: boolean;
  agents: AgentSummary[];
};

type ReportInsertPayload = {
  template_id: string | null;
  user_id: string;
  status: 'GENERATING';
  name: string;
  prompt: string;
  include_charts: boolean;
  semantic_connection_id?: string | null;
};

type SupabaseLikeError = {
  code?: string;
  message?: string;
  details?: string;
  hint?: string;
};

type CatalogConnection = {
  id: string;
  status?: string;
  is_default?: boolean;
};

type SemanticCatalogResponse = {
  selected_connection_id?: string | null;
  connection_id?: string | null;
  connections?: CatalogConnection[];
};

type ToastState = {
  id: number;
  message: string;
};

function supabaseErrorText(error: SupabaseLikeError | null | undefined): string {
  return [error?.code, error?.message, error?.details, error?.hint]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function isMissingReportConnectionColumn(error: SupabaseLikeError | null | undefined): boolean {
  const text = supabaseErrorText(error);
  return (
    text.includes("semantic_connection_id") &&
    (
      text.includes("schema cache") ||
      text.includes("column") ||
      text.includes("could not find") ||
      text.includes("pgrst204") ||
      text.includes("pgrst205")
    )
  );
}

function isReportConnectionForeignKeyError(error: SupabaseLikeError | null | undefined): boolean {
  const text = supabaseErrorText(error);
  return (
    (text.includes("semantic_connection_id") || text.includes("connector_instances")) &&
    (
      text.includes("foreign key") ||
      text.includes("violates") ||
      text.includes("23503")
    )
  );
}

function formatCreateReportError(error: SupabaseLikeError | null | undefined): string {
  if (!error) return "No se pudo guardar el informe.";
  return error.message || error.details || error.hint || "No se pudo guardar el informe.";
}

function pickCatalogConnectionId(catalog: SemanticCatalogResponse, fallback?: string | null): string | null {
  const selected = catalog.selected_connection_id || catalog.connection_id;
  if (selected) return selected;

  const readyConnections = (catalog.connections ?? []).filter((connection) =>
    connection.id && ["ready", "connected"].includes(connection.status ?? ""),
  );
  const defaultReady = readyConnections.filter((connection) => connection.is_default);
  if (defaultReady.length === 1) return defaultReady[0].id;
  if (readyConnections.length === 1) return readyConnections[0].id;

  return fallback || null;
}

export default function InformesPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [mobileView, setMobileView] = useState<'list' | 'reader'>('list');
  const [toast, setToast] = useState<ToastState | null>(null);
  
  const supabase = createClient();

  const fetchInitialData = useCallback(async () => {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return;

    // Fetch user reports
    const { data: reportsData, error: reportsError } = await supabase
      .from('reports')
      .select(reportSelect)
      .eq('user_id', user.id)
      .order('created_at', { ascending: false });

    if (reportsError) {
      console.error("Error fetching reports:", reportsError);
    }
    
    if (reportsData) {
      setReports(reportsData as unknown as Report[]);
      
      // Preserve current selection if it still exists, otherwise select the first one
      setSelectedId(prevId => {
        const stillExists = (reportsData as ReportRow[]).some((r) => r.id === prevId);
        if (prevId && stillExists) {
          return prevId;
        }
        return reportsData.length > 0 ? reportsData[0].id : "";
      });
    }
    setIsLoading(false);
  }, [supabase]);

  useEffect(() => {
    const initialFetchTimeout = window.setTimeout(() => {
      void fetchInitialData();
    }, 0);

    // Setup Realtime Subscription
    const channel = supabase.channel('schema-db-changes')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'reports' },
        () => {
          fetchInitialData();
        }
      )
      .subscribe();

    return () => {
      window.clearTimeout(initialFetchTimeout);
      supabase.removeChannel(channel);
    };
  }, [supabase, fetchInitialData]);

  useEffect(() => {
    if (!toast) return;

    const timeout = window.setTimeout(() => {
      setToast(null);
    }, 2600);

    return () => window.clearTimeout(timeout);
  }, [toast]);

  // Polling for pending/generating reports
  useEffect(() => {
    const hasPendingReports = reports.some(r => r.status === 'PENDING' || r.status === 'GENERATING');
    if (!hasPendingReports) return;

    const interval = setInterval(async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return;

      const { data: reportsData, error: reportsError } = await supabase
        .from('reports')
        .select(reportSelect)
        .eq('user_id', user.id)
        .order('created_at', { ascending: false });

      if (reportsError) {
        console.error("Error polling reports:", reportsError);
      }
      
      if (reportsData) {
        setReports(reportsData as unknown as Report[]);
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [reports, supabase]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (reports.length === 0) return;

      const currentIndex = reports.findIndex(r => r.id === selectedId);
      if (currentIndex === -1) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const nextIndex = currentIndex < reports.length - 1 ? currentIndex + 1 : currentIndex;
        setSelectedId(reports[nextIndex].id);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        const prevIndex = currentIndex > 0 ? currentIndex - 1 : currentIndex;
        setSelectedId(reports[prevIndex].id);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedId, reports]);

  const handleCreateReport = async (reportData: CreateReportPayload) => {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return;

    const fetchCatalogConnection = async (connectionId?: string | null): Promise<string | null> => {
      const { headers } = await getSupabaseAuthHeaders();
      if (!headers.Authorization) {
        return connectionId || null;
      }

      const query = connectionId ? `?connection_id=${encodeURIComponent(connectionId)}` : "";
      const response = await fetch(`${apiBaseUrl}/semantic-model/catalog${query}`, { headers });
      if (!response.ok) {
        if (connectionId) return null;
        throw new Error(await response.text() || `HTTP ${response.status}`);
      }

      const catalog = await response.json() as SemanticCatalogResponse;
      return pickCatalogConnectionId(catalog, connectionId);
    };

    const resolveSemanticConnectionId = async (): Promise<string | null> => {
      const localConnectionId = window.localStorage.getItem("nyro_active_connection_id");
      if (localConnectionId) {
        try {
          const resolved = await fetchCatalogConnection(localConnectionId);
          if (resolved) {
            window.localStorage.setItem("nyro_active_connection_id", resolved);
            return resolved;
          }
        } catch (error) {
          console.warn("No se pudo validar la conexion semantica cacheada para informes:", error);
        }
      }

      try {
        const resolved = await fetchCatalogConnection(null);
        if (resolved) {
          window.localStorage.setItem("nyro_active_connection_id", resolved);
          return resolved;
        }
      } catch (error) {
        console.warn("No se pudo resolver la conexion semantica activa para informes:", error);
      }

      return localConnectionId || null;
    };

    const insertReport = async (connectionId: string | null, includeConnectionColumn: boolean) => {
      const payload: ReportInsertPayload = {
        template_id: null,
        user_id: user.id,
        status: 'GENERATING',
        name: reportData.name,
        prompt: reportData.prompt,
        include_charts: false,
      };
      if (includeConnectionColumn) {
        payload.semantic_connection_id = connectionId;
      }

      return supabase
        .from('reports')
        .insert(payload)
        .select('id')
        .single();
    };

    let semanticConnectionId = await resolveSemanticConnectionId();
    let { data, error } = await insertReport(semanticConnectionId, true);

    if (error && isReportConnectionForeignKeyError(error)) {
      window.localStorage.removeItem("nyro_active_connection_id");
      semanticConnectionId = await resolveSemanticConnectionId();
      if (semanticConnectionId) {
        const retry = await insertReport(semanticConnectionId, true);
        data = retry.data;
        error = retry.error;
      }
    }

    if (error && (isMissingReportConnectionColumn(error) || isReportConnectionForeignKeyError(error))) {
      const retry = await insertReport(null, false);
      data = retry.data;
      error = retry.error;
    }

    if (error || !data) {
      console.error("Error creating report in DB:", error);
      alert(`Error al crear el informe. ${formatCreateReportError(error)}`);
      return;
    }

    // 2. Insert intermediate agent relationships
    if (reportData.agents.length > 0) {
      const relationPayloads = reportData.agents.map((agent) => ({
        report_id: data.id,
        agent_id: agent.id
      }));

      const { error: relationError } = await supabase
        .from('report_agents')
        .insert(relationPayloads);

      if (relationError) {
        console.error("Error creating report agents relationships in DB:", relationError);
      }
    }

    try {
      const triggerRes = await fetch(`${apiBaseUrl}/reports/generate-report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report_id: data.id, force: true })
      });

      if (!triggerRes.ok) {
        const detail = await triggerRes.text();
        throw new Error(detail || `HTTP ${triggerRes.status}`);
      }
    } catch (triggerError) {
      console.error("Error triggering report generation:", triggerError);
      await supabase
        .from('reports')
        .update({
          status: 'FAILED',
          error_log: `No se pudo iniciar el worker local de informes: ${triggerError instanceof Error ? triggerError.message : String(triggerError)}`
        })
        .eq('id', data.id);
    }

    setSelectedId(data.id);
    setMobileView('reader');
    setIsModalOpen(false);

    // Refresh reports list to immediately show the pending report in the feed
    await fetchInitialData();
  };

  const handleDeleteReport = async (id: string) => {
    const { error } = await supabase
      .from('reports')
      .delete()
      .eq('id', id);
    
    if (error) {
      console.error('Error deleting report:', error);
      alert('Error al eliminar el informe');
      return;
    }

    const currentIndex = reports.findIndex(r => r.id === id);
    if (currentIndex !== -1) {
      const nextId = reports.length > 1 
        ? reports[currentIndex === reports.length - 1 ? currentIndex - 1 : currentIndex + 1].id 
        : "";
      setSelectedId(nextId);
      if (!nextId) setMobileView('list');
    }

    // Refresh reports list to remove the deleted report
    await fetchInitialData();
    setToast({ id: Date.now(), message: "Informe eliminado" });
  };

  const handleRegenerateReport = async (id: string) => {
    try {
      const triggerRes = await fetch(`${apiBaseUrl}/reports/${id}/regenerate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      if (!triggerRes.ok) {
        const detail = await triggerRes.text();
        throw new Error(detail || `HTTP ${triggerRes.status}`);
      }

      await fetchInitialData();
    } catch (error) {
      console.error("Error regenerating report:", error);
      alert(`Error al regenerar el informe. ${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const selectedReport = reports.find(r => r.id === selectedId);

  return (
    <div className="flex h-full w-full relative overflow-hidden">
      {/* Columna 1: Sidebar (20%) */}
      <InformesSidebar onNewReport={() => setIsModalOpen(true)} />

      <button
        onClick={() => setIsModalOpen(true)}
        className="md:hidden absolute right-4 top-3 z-40 flex h-10 w-10 items-center justify-center rounded-xl bg-zinc-100 text-zinc-950 shadow-lg shadow-black/30 transition-colors hover:bg-white"
        title="Crear informe"
      >
        <FilePlus2 size={18} />
      </button>

      {/* Columna 2: Intelligence Feed (30%) */}
      {isLoading ? (
        <section className="w-full md:w-[30%] md:min-w-[320px] md:max-w-[380px] bg-zinc-950/60 md:border-r border-zinc-900 flex items-center justify-center">
          <div className="w-6 h-6 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin"></div>
        </section>
      ) : (
        <InformesFeed
          reports={reports}
          selectedId={selectedId}
          className={mobileView === 'reader' ? 'hidden md:flex' : undefined}
          onSelect={(id) => {
            setSelectedId(id);
            setMobileView('reader');
          }}
        />
      )}

      {/* Columna 3: Reader (50%) */}
      {selectedReport ? (
        <div className={`${mobileView === 'list' ? 'hidden' : 'flex'} md:flex h-full flex-1 min-w-0`}>
          <InformesReader
            report={selectedReport}
            onDelete={handleDeleteReport}
            onRegenerate={handleRegenerateReport}
            onBack={() => setMobileView('list')}
          />
        </div>
      ) : (
        <section className="hidden md:flex flex-1 min-w-[500px] h-full flex-col bg-zinc-950/60 items-center justify-center text-zinc-500">
          {isLoading ? (
            <p>Cargando informes...</p>
          ) : (
            <p>Selecciona un informe para comenzar o crea uno nuevo.</p>
          )}
        </section>
      )}

      {/* Create Report Modal */}
      <CreateReportModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCreateReport={handleCreateReport}
      />

      {toast && (
        <div
          key={toast.id}
          className="pointer-events-none absolute bottom-5 left-1/2 z-[90] flex -translate-x-1/2 items-center gap-2 rounded-md border border-zinc-800/90 bg-[#101011]/95 px-3.5 py-2 text-xs font-medium text-zinc-200 shadow-2xl shadow-black/50 backdrop-blur-md animate-in fade-in slide-in-from-bottom-2 duration-200"
          role="status"
          aria-live="polite"
        >
          <CheckCircle2 size={14} className="text-emerald-400" />
          <span>{toast.message}</span>
        </div>
      )}
    </div>
  );
}
