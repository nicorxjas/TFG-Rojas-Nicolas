"use client";

import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { 
  Plus, 
  Bot, 
  Cpu, 
  Search, 
  Grid, 
  List, 
  ChevronLeft, 
  ChevronRight
} from "lucide-react";
import { AgentCard } from "@/components/agentes/AgentCard";
import { AgentModal } from "@/components/agentes/AgentModal";
import { AgentVisualIcon } from "@/components/agentes/agent-icon";
import { Skill } from "@/app/skills/types";
import { Agent } from "./types";

type AgentRow = {
  id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  category: string | null;
  icon_type?: "icon" | "emoji" | null;
  icon_name?: string | null;
  icon_color?: string | null;
  icon_emoji?: string | null;
  created_at: string;
};

type SkillRow = {
  id: string;
  name: string;
  description: string | null;
  instruction: string;
  created_at: string;
  updated_at: string | null;
};

type SkillAgentRow = {
  skill_id: string;
  agent_id: string;
};

// ── Seed data ──────────────────────────────────────────────────────────────
export const SEED_AGENTS: Agent[] = [
  {
    id: "1",
    name: "Agente Financiero",
    description: "Analiza métricas de ingresos, márgenes, costos y KPIs financieros clave para detectar desvíos y oportunidades.",
    systemPrompt: "Eres un experto en análisis financiero empresarial. Evalúas los datos de ingresos, costos y márgenes para identificar tendencias, alertas y oportunidades de mejora. Comunica los hallazgos con claridad y precisión.",
    category: "finanzas",
    createdAt: new Date(Date.now() - 7 * 86400000).toISOString(),
  },
  {
    id: "2",
    name: "Agente de Churn",
    description: "Identifica patrones de cancelación, segmentos en riesgo y factores predictivos de abandono de clientes.",
    systemPrompt: "Eres un especialista en retención de clientes y análisis de churn. Analizas comportamientos, frecuencia de uso y señales tempranas de abandono para generar insights accionables que reduzcan la tasa de cancelación.",
    category: "churn",
    createdAt: new Date(Date.now() - 3 * 86400000).toISOString(),
  },
  {
    id: "3",
    name: "Agente de Oportunidades",
    description: "Detecta segmentos de alto potencial, up-sell y cross-sell basados en el comportamiento de compra.",
    systemPrompt: "Eres un analista de oportunidades comerciales. Tu objetivo es identificar segmentos de clientes con alto potencial de crecimiento, oportunidades de upsell y patrones de compra que permitan generar más valor.",
    category: "oportunidad",
    createdAt: new Date(Date.now() - 1 * 86400000).toISOString(),
  },
  {
    id: "4",
    name: "Agente de Riesgos",
    description: "Evalúa exposiciones, concentraciones de riesgo y señales de alerta temprana en la cartera de clientes.",
    systemPrompt: "Eres un experto en gestión de riesgos. Evalúas la concentración de cartera, exposición crediticia, anomalías operativas y señales de alerta que puedan impactar negativamente al negocio.",
    category: "riesgos",
    createdAt: new Date().toISOString(),
  },
];

// ──────────────────────────────────────────────────────────────────────────

export default function AgentesPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillsSyncAvailable, setSkillsSyncAvailable] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [modalMode, setModalMode] = useState<"create" | "edit" | "view" | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  const supabase = createClient();

  // Load agents from Supabase on mount
  useEffect(() => {
    const fetchAgents = async () => {
      setIsLoading(true);

      const [agentsResult, skillsResult, relationsResult] = await Promise.all([
        supabase.from("agents").select("*").order("created_at", { ascending: false }),
        supabase.from("skills").select("*").order("name", { ascending: true }),
        supabase.from("skill_agents").select("*"),
      ]);

      if (agentsResult.error) {
        console.error("Error fetching agents:", agentsResult.error);
      }
      if (skillsResult.error) {
        console.error("Error fetching skills:", skillsResult.error);
        setSkillsSyncAvailable(false);
      }
      if (relationsResult.error) {
        console.error("Error fetching skill agents:", relationsResult.error);
        setSkillsSyncAvailable(false);
      }

      const mappedSkills: Skill[] = ((skillsResult.data ?? []) as SkillRow[]).map((skill) => ({
        id: skill.id,
        name: skill.name,
        description: skill.description ?? "",
        instruction: skill.instruction,
        agents: [],
        createdAt: skill.created_at,
        updatedAt: skill.updated_at ?? undefined,
      }));
      const skillsById = new Map(mappedSkills.map((skill) => [skill.id, skill]));
      const relations = (relationsResult.data ?? []) as SkillAgentRow[];

      const mappedAgents = ((agentsResult.data ?? []) as AgentRow[]).map((a) => ({
        id: a.id,
        name: a.name,
        description: a.description ?? "",
        systemPrompt: a.system_prompt,
        category: a.category ?? "general",
        iconType: a.icon_type ?? "icon",
        iconName: a.icon_name ?? undefined,
        iconColor: a.icon_color ?? undefined,
        iconEmoji: a.icon_emoji ?? undefined,
        skills: relations
          .filter((relation) => relation.agent_id === a.id)
          .map((relation) => skillsById.get(relation.skill_id))
          .filter((skill): skill is Skill => Boolean(skill)),
        createdAt: a.created_at,
      }));

      setSkills(mappedSkills);
      setAgents(mappedAgents);
      setIsLoading(false);
    };

    fetchAgents();
  }, [supabase]);

  // ── Handlers ──────────────────────────────────────────────────────────
  const openCreate = () => {
    setSelectedAgent(null);
    setModalMode("create");
  };

  const openView = (agent: Agent) => {
    setSelectedAgent(agent);
    setModalMode("edit");
  };

  const closeModal = () => {
    setModalMode(null);
    setSelectedAgent(null);
  };

  const handleSave = async (agent: Agent) => {
    const dbPayload = {
      id: agent.id,
      name: agent.name,
      description: agent.description,
      system_prompt: agent.systemPrompt,
      category: agent.category,
      icon_type: agent.iconType ?? "icon",
      icon_name: agent.iconName ?? null,
      icon_color: agent.iconColor ?? null,
      icon_emoji: agent.iconEmoji ?? null
    };

    const { error } = await supabase
      .from("agents")
      .upsert(dbPayload);

    if (error) {
      console.error("Error saving agent:", error);
      alert(`Error al guardar el agente: ${error.message}`);
      return;
    }

    if (skillsSyncAvailable) {
      const { error: deleteSkillRelationsError } = await supabase
        .from("skill_agents")
        .delete()
        .eq("agent_id", agent.id);

      if (deleteSkillRelationsError) {
        console.error("Error clearing agent skills:", deleteSkillRelationsError);
        alert("Error al actualizar skills del agente");
        return;
      }

      if ((agent.skills ?? []).length > 0) {
        const { error: insertSkillRelationsError } = await supabase
          .from("skill_agents")
          .insert((agent.skills ?? []).map((skill) => ({
            skill_id: skill.id,
            agent_id: agent.id,
          })));

        if (insertSkillRelationsError) {
          console.error("Error assigning agent skills:", insertSkillRelationsError);
          alert("Error al asignar skills al agente");
          return;
        }
      }
    }

    setAgents((prev) => {
      const exists = prev.find((a) => a.id === agent.id);
      if (exists) {
        return prev.map((a) => (a.id === agent.id ? agent : a));
      }
      return [agent, ...prev];
    });
    closeModal();
  };

  const handleDelete = async (id: string) => {
    const { error } = await supabase
      .from("agents")
      .delete()
      .eq("id", id);

    if (error) {
      console.error("Error deleting agent:", error);
      alert("Error al eliminar el agente");
      return;
    }

    setAgents((prev) => prev.filter((a) => a.id !== id));
  };

  // Filter agents by search query
  const filteredAgents = agents.filter(
    (agent) =>
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.category?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className={`relative flex-1 flex flex-col h-full bg-[#0a0a0c] ${modalMode ? "overflow-hidden" : "overflow-y-auto"}`}>

      {/* ── Top Bar: High Fidelity Search Header ── */}
      <div className="sticky top-0 z-40 bg-[#0a0a0c] border-b border-zinc-900/60 px-4 md:px-8 py-4 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 md:gap-0">
        {/* Modern Search Input resembling Spline layout */}
        <div className="relative w-full md:w-80">
          <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            placeholder="Search..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-zinc-900/40 border border-zinc-800/80 rounded-full pl-9 pr-12 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-700/80 transition-colors"
          />
          <div className="hidden md:block absolute right-3 top-1/2 -translate-y-1/2 bg-zinc-950 border border-zinc-800/80 rounded px-1.5 py-0.5 text-[9px] font-mono text-zinc-500 select-none pointer-events-none">
            ⌘K
          </div>
        </div>

        {/* Dashboard Title/Header Right */}
        <div className="hidden md:flex items-center gap-3">
          <span className="text-xs text-zinc-500 cursor-pointer hover:text-zinc-300 transition-colors">Dashboard</span>
          <span className="text-[10px] text-zinc-700 select-none">/</span>
          <span className="text-xs text-zinc-300 font-medium">Agentes</span>
        </div>
      </div>

      {/* ── Main Layout Inner ── */}
      <div className="flex-1 px-4 md:px-8 py-5 md:py-7 flex flex-col justify-between">
        <div>
          {/* ── Sub Header: Section Title & Grid Toggles ── */}
          <div className="flex flex-col md:flex-row md:items-center justify-between mb-6 md:mb-8 gap-4">
            <div className="flex items-center justify-between gap-3">
              <div className="w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 flex items-center justify-center">
                <Cpu size={16} className="text-zinc-300" />
              </div>
              <div>
                <h1 className="text-base font-semibold text-zinc-100">Agentes</h1>
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  {filteredAgents.length} de {agents.length} configurado{agents.length !== 1 ? "s" : ""}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {/* List / Grid View Selector */}
              <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-lg p-0.5 flex items-center">
                <button
                  onClick={() => setViewMode("list")}
                  className={`p-1.5 rounded-md transition-colors ${
                    viewMode === "list"
                      ? "bg-zinc-800 text-zinc-200"
                      : "text-zinc-500 hover:text-zinc-300"
                  }`}
                >
                  <List size={13} />
                </button>
                <button
                  onClick={() => setViewMode("grid")}
                  className={`p-1.5 rounded-md transition-colors ${
                    viewMode === "grid"
                      ? "bg-zinc-800 text-zinc-200"
                      : "text-zinc-500 hover:text-zinc-300"
                  }`}
                >
                  <Grid size={13} />
                </button>
              </div>

              {/* Add Agent Button */}
              <button
                onClick={openCreate}
                className="flex items-center gap-1.5 px-3 py-2 md:py-1.5 bg-zinc-100 hover:bg-white text-zinc-950 text-xs font-semibold rounded-lg transition-colors"
              >
                <Plus size={13} />
                Nuevo agente
              </button>
            </div>
          </div>

          {/* ── Content Grid / List ── */}
          {isLoading ? (
            <div className="flex items-center justify-center py-32">
              <div className="w-8 h-8 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin"></div>
            </div>
          ) : filteredAgents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="w-14 h-14 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center mb-5">
                <Bot size={26} className="text-zinc-600" />
              </div>
              <h2 className="text-sm font-medium text-zinc-300 mb-1.5">Sin agentes encontrados</h2>
              <p className="text-xs text-zinc-600 max-w-[250px] leading-relaxed">
                Prueba buscando otro término o crea un nuevo agente especializado.
              </p>
              <button
                onClick={openCreate}
                className="mt-6 flex items-center gap-1.5 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium rounded-lg transition-colors"
              >
                <Plus size={13} />
                Crear agente
              </button>
            </div>
          ) : viewMode === "grid" ? (
            /* Grid View - high density layout matching the smaller 40% cards */
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 md:gap-4">
              {/* "New Agent" Dotted Card resembling custom design block */}
              <button
                onClick={openCreate}
                className="group relative aspect-[3.2/4] min-h-[135px] bg-zinc-900/10 border border-dashed border-zinc-800/80 rounded-xl
                           flex flex-col items-center justify-center gap-2 transition-all duration-300
                           hover:border-zinc-700/80 hover:bg-zinc-900/20 hover:shadow-md cursor-pointer"
              >
                <div className="w-9 h-9 rounded-lg bg-zinc-900/80 group-hover:bg-zinc-800 border border-zinc-800 group-hover:border-zinc-700 flex items-center justify-center transition-all duration-300">
                  <Plus size={14} className="text-zinc-500 group-hover:text-zinc-300" />
                </div>
                <div className="text-center">
                  <span className="text-xs font-semibold text-zinc-500 group-hover:text-zinc-300 transition-colors">
                    Agregar Agente
                  </span>
                  <p className="text-[9px] text-zinc-600 mt-0.5 max-w-[120px] mx-auto px-1 leading-snug">
                    Nueva inteligencia
                  </p>
                </div>
              </button>

              {filteredAgents.map((agent) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  onClick={() => openView(agent)}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          ) : (
            /* List View */
            <div className="border border-zinc-800/80 rounded-2xl bg-zinc-900/20 overflow-hidden divide-y divide-zinc-900">
              {filteredAgents.map((agent) => (
                <div
                  key={agent.id}
                  onClick={() => openView(agent)}
                  className="flex items-center justify-between p-4 hover:bg-zinc-900/40 cursor-pointer transition-colors"
                >
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center">
                      <AgentVisualIcon agent={agent} size={18} />
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-zinc-200">{agent.name}</h4>
                      <p className="text-xs text-zinc-500 capitalize">{agent.category}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-zinc-500 hidden md:block max-w-[320px] truncate">
                      {agent.description}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(agent.id);
                      }}
                      className="text-zinc-600 hover:text-rose-400 p-1.5 rounded transition-colors"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Elegant Footer with Pagination resembling visual style ── */}
        {!modalMode && (
        <div className="mt-10 md:mt-14 pt-6 md:pt-8 border-t border-zinc-900/60 flex items-center justify-center w-full">
          {/* Pagination Controls */}
          <div className="flex items-center gap-1.5 select-none">
            <button className="w-8 h-8 rounded-full border border-zinc-800 bg-zinc-900/20 flex items-center justify-center text-zinc-500 hover:text-zinc-300 hover:border-zinc-700 transition-colors">
              <ChevronLeft size={13} />
            </button>
            <button className="w-8 h-8 rounded-full border border-zinc-800 bg-zinc-850 text-zinc-200 flex items-center justify-center text-xs font-semibold">
              1
            </button>
            <button className="w-8 h-8 rounded-full border border-transparent bg-transparent text-zinc-500 hover:text-zinc-300 flex items-center justify-center text-xs font-semibold">
              2
            </button>
            <button className="w-8 h-8 rounded-full border border-transparent bg-transparent text-zinc-500 hover:text-zinc-300 flex items-center justify-center text-xs font-semibold">
              3
            </button>
            <span className="text-zinc-600 px-1 font-mono text-xs">...</span>
            <button className="w-8 h-8 rounded-full border border-transparent bg-transparent text-zinc-500 hover:text-zinc-300 flex items-center justify-center text-xs font-semibold">
              21
            </button>
            <button className="w-8 h-8 rounded-full border border-zinc-800 bg-zinc-900/20 flex items-center justify-center text-zinc-500 hover:text-zinc-300 hover:border-zinc-700 transition-colors">
              <ChevronRight size={13} />
            </button>
          </div>
        </div>
        )}
      </div>

      {/* ── Modal ── */}
      {(modalMode === "create" || modalMode === "edit") && (
        <AgentModal
          agent={selectedAgent}
          skills={skills}
          onClose={closeModal}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
