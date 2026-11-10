"use client";

import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, MoreHorizontal, Plus, Search, Sparkles, Trash2, Users } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { Agent } from "@/app/agentes/types";
import { AgentAvatarGroup } from "@/components/agentes/AgentAvatarGroup";
import { SkillModal } from "@/components/skills/SkillModal";
import { Skill } from "./types";

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

type ToastState = {
  id: number;
  message: string;
};

function mapAgent(row: AgentRow): Agent {
  return {
    id: row.id,
    name: row.name,
    description: row.description ?? "",
    systemPrompt: row.system_prompt,
    category: row.category ?? "general",
    iconType: row.icon_type ?? "icon",
    iconName: row.icon_name ?? undefined,
    iconColor: row.icon_color ?? undefined,
    iconEmoji: row.icon_emoji ?? undefined,
    createdAt: row.created_at,
  };
}

function formatDate(date: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
  }).format(new Date(date));
}

export default function SkillsPage() {
  const supabase = createClient();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);

      const [skillsResult, agentsResult, relationsResult] = await Promise.all([
        supabase.from("skills").select("*").order("created_at", { ascending: false }),
        supabase.from("agents").select("*").order("name", { ascending: true }),
        supabase.from("skill_agents").select("*"),
      ]);

      if (skillsResult.error) {
        console.error("Error fetching skills:", skillsResult.error);
      }
      if (agentsResult.error) {
        console.error("Error fetching agents:", agentsResult.error);
      }
      if (relationsResult.error) {
        console.error("Error fetching skill agents:", relationsResult.error);
      }

      const mappedAgents = ((agentsResult.data ?? []) as AgentRow[]).map(mapAgent);
      const agentsById = new Map(mappedAgents.map((agent) => [agent.id, agent]));
      const relations = (relationsResult.data ?? []) as SkillAgentRow[];

      const mappedSkills = ((skillsResult.data ?? []) as SkillRow[]).map((skill) => ({
        id: skill.id,
        name: skill.name,
        description: skill.description ?? "",
        instruction: skill.instruction,
        agents: relations
          .filter((relation) => relation.skill_id === skill.id)
          .map((relation) => agentsById.get(relation.agent_id))
          .filter((agent): agent is Agent => Boolean(agent)),
        createdAt: skill.created_at,
        updatedAt: skill.updated_at ?? undefined,
      }));

      setAgents(mappedAgents);
      setSkills(mappedSkills);
      setIsLoading(false);
    };

    fetchData();
  }, [supabase]);

  useEffect(() => {
    if (!toast) return;

    const timeout = window.setTimeout(() => {
      setToast(null);
    }, 2600);

    return () => window.clearTimeout(timeout);
  }, [toast]);

  const filteredSkills = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return skills;

    return skills.filter((skill) => (
      skill.name.toLowerCase().includes(query) ||
      skill.description.toLowerCase().includes(query) ||
      skill.agents.some((agent) => agent.name.toLowerCase().includes(query))
    ));
  }, [searchQuery, skills]);

  const openCreate = () => {
    setSelectedSkill(null);
    setEditorOpen(true);
  };

  const openEdit = (skill: Skill) => {
    setSelectedSkill(skill);
    setEditorOpen(true);
  };

  const closeEditor = () => {
    setSelectedSkill(null);
    setEditorOpen(false);
  };

  const handleSave = async (skill: Skill) => {
    const { error: skillError } = await supabase
      .from("skills")
      .upsert({
        id: skill.id,
        name: skill.name,
        description: skill.description,
        instruction: skill.instruction,
        updated_at: new Date().toISOString(),
      });

    if (skillError) {
      console.error("Error saving skill:", skillError);
      alert("Error al guardar la skill");
      return;
    }

    const { error: deleteRelationError } = await supabase
      .from("skill_agents")
      .delete()
      .eq("skill_id", skill.id);

    if (deleteRelationError) {
      console.error("Error clearing skill agents:", deleteRelationError);
      alert("Error al actualizar agentes de la skill");
      return;
    }

    if (skill.agents.length > 0) {
      const { error: insertRelationError } = await supabase
        .from("skill_agents")
        .insert(skill.agents.map((agent) => ({
          skill_id: skill.id,
          agent_id: agent.id,
        })));

      if (insertRelationError) {
        console.error("Error assigning skill agents:", insertRelationError);
        alert("Error al asignar agentes a la skill");
        return;
      }
    }

    setSkills((current) => {
      const exists = current.some((item) => item.id === skill.id);
      if (exists) {
        return current.map((item) => (item.id === skill.id ? skill : item));
      }
      return [skill, ...current];
    });
    closeEditor();
  };

  const handleDelete = async (skillId: string) => {
    const { error } = await supabase
      .from("skills")
      .delete()
      .eq("id", skillId);

    if (error) {
      console.error("Error deleting skill:", error);
      alert("Error al eliminar la skill");
      return;
    }

    setSkills((current) => current.filter((skill) => skill.id !== skillId));
    setToast((current) => ({ id: (current?.id ?? 0) + 1, message: "Skill eliminada" }));
  };

  return (
    <div className="relative flex-1 overflow-y-auto bg-[#f6f7f9] font-sans text-zinc-950 dark:bg-[#0a0a0b] dark:text-zinc-100">
      <div className="mx-auto flex min-h-full w-full flex-col px-5 py-8 md:px-8 md:py-10">
        <header className="mb-10 flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal text-zinc-950 dark:text-zinc-50">Skills</h1>
            <div className="mt-4 flex flex-col gap-2 sm:flex-row">
              <div className="relative w-full sm:w-[360px]">
                <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-400 dark:text-zinc-500" />
                <input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter by name..."
                  className="h-9 w-full rounded-md border border-zinc-200 bg-white pl-9 pr-3 text-sm text-zinc-950 outline-none transition-colors placeholder:text-zinc-400 hover:border-zinc-300 focus:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-900/75 dark:text-zinc-200 dark:placeholder:text-zinc-500 dark:hover:border-zinc-700 dark:focus:border-zinc-600"
                />
              </div>
            </div>
          </div>

          <button
            onClick={openCreate}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-black px-3 text-xs font-semibold text-[#ffffff] transition-colors hover:bg-[#24262b] dark:bg-zinc-100 dark:text-zinc-950 dark:hover:bg-white"
          >
            <Plus size={15} />
            Nueva Skill
          </button>
        </header>

        <section className="flex-1">
          <div className="grid grid-cols-[40px_minmax(180px,1.2fr)_minmax(180px,1.4fr)_minmax(180px,1fr)_120px_44px] items-center px-3 pb-2 text-xs text-zinc-500 dark:text-zinc-500">
            <div />
            <div>Name</div>
            <div>Description</div>
            <div>Agents</div>
            <div>Created</div>
            <div />
          </div>

          {isLoading ? (
            <div className="flex items-center justify-center py-24">
              <div className="h-7 w-7 animate-spin rounded-full border-2 border-zinc-200 border-t-zinc-500 dark:border-zinc-800 dark:border-t-zinc-400" />
            </div>
          ) : filteredSkills.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-zinc-200 bg-white/50 py-24 text-center dark:border-zinc-800 dark:bg-transparent">
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
                <Sparkles size={22} className="text-zinc-400 dark:text-zinc-500" />
              </div>
              <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-300">Sin skills encontradas</h2>
              <p className="mt-1 max-w-[280px] text-xs leading-relaxed text-zinc-500 dark:text-zinc-600">
                Crea una skill reutilizable para darle capacidades compartidas a tus agentes.
              </p>
              <button
                onClick={openCreate}
                className="mt-5 rounded-full bg-black px-4 py-2 text-xs font-semibold text-[#ffffff] transition-colors hover:bg-[#24262b] dark:bg-zinc-100 dark:text-zinc-950 dark:hover:bg-white"
              >
                Crear skill
              </button>
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white/70 shadow-sm shadow-zinc-200/50 dark:border-zinc-900/60 dark:bg-transparent dark:shadow-none">
              {filteredSkills.map((skill) => (
                <div
                  key={skill.id}
                  onClick={() => openEdit(skill)}
                  className="grid min-h-12 cursor-pointer grid-cols-[40px_minmax(180px,1.2fr)_minmax(180px,1.4fr)_minmax(180px,1fr)_120px_44px] items-center border-b border-zinc-200/80 bg-white/70 px-3 text-sm transition-colors last:border-b-0 hover:bg-zinc-50 dark:border-zinc-900/70 dark:bg-zinc-900/35 dark:hover:bg-zinc-900/60"
                >
                  <div className="flex items-center">
                    <span className="h-3.5 w-3.5 rounded-[4px] border border-zinc-200 bg-white dark:border-zinc-700 dark:bg-transparent" />
                  </div>
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="truncate font-semibold text-zinc-950 dark:text-zinc-200">{skill.name}</span>
                  </div>
                  <div className="truncate text-sm font-medium text-zinc-700 dark:text-zinc-400">
                    {skill.description || "Sin descripcion"}
                  </div>
                  <div className="flex min-w-0 items-center">
                    {skill.agents.length === 0 ? (
                      <span className="inline-flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-600">
                        <Users size={13} />
                        Sin agentes
                      </span>
                    ) : (
                      <AgentAvatarGroup agents={skill.agents} />
                    )}
                  </div>
                  <div className="text-sm text-zinc-500 dark:text-zinc-500">{formatDate(skill.createdAt)}</div>
                  <div className="flex justify-end">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(skill.id);
                      }}
                      className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-rose-500 dark:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-rose-400"
                      aria-label={`Eliminar ${skill.name}`}
                    >
                      <Trash2 size={15} />
                    </button>
                    <MoreHorizontal size={16} className="hidden text-zinc-400 dark:text-zinc-700" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {editorOpen && (
        <SkillModal
          skill={selectedSkill}
          agents={agents}
          onClose={closeEditor}
          onSave={handleSave}
        />
      )}

      {toast && (
        <div
          key={toast.id}
          className="pointer-events-none fixed bottom-5 left-1/2 z-[100] flex -translate-x-1/2 items-center gap-2 rounded-md border border-zinc-800/90 bg-[#101011]/95 px-3.5 py-2 text-xs font-medium text-zinc-200 shadow-2xl shadow-black/50 backdrop-blur-md animate-in fade-in slide-in-from-bottom-2 duration-200"
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
