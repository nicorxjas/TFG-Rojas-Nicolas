"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Search, UserPlus, X } from "lucide-react";
import { Agent } from "@/app/agentes/types";
import { Skill } from "@/app/skills/types";
import { AgentVisualIcon } from "@/components/agentes/agent-icon";

interface SkillModalProps {
  skill?: Skill | null;
  agents: Agent[];
  onClose: () => void;
  onSave: (skill: Skill) => void;
}

export function SkillModal({ skill, agents, onClose, onSave }: SkillModalProps) {
  const isEdit = !!skill;
  const [name, setName] = useState(skill?.name ?? "");
  const [description, setDescription] = useState(skill?.description ?? "");
  const [instruction, setInstruction] = useState(skill?.instruction ?? "");
  const [selectedAgents, setSelectedAgents] = useState<Agent[]>(skill?.agents ?? []);
  const [agentSearch, setAgentSearch] = useState("");
  const [agentDropdownOpen, setAgentDropdownOpen] = useState(false);
  const [nameError, setNameError] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && agentDropdownOpen) {
        setAgentDropdownOpen(false);
        return;
      }
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [agentDropdownOpen, onClose]);

  useEffect(() => {
    const onPointerDown = (e: MouseEvent) => {
      if (!dropdownRef.current?.contains(e.target as Node)) {
        setAgentDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  const availableAgents = useMemo(() => {
    const selectedIds = new Set(selectedAgents.map((agent) => agent.id));
    const query = agentSearch.trim().toLowerCase();

    return agents.filter((agent) => {
      if (selectedIds.has(agent.id)) return false;
      if (!query) return true;
      return (
        agent.name.toLowerCase().includes(query) ||
        agent.description.toLowerCase().includes(query) ||
        agent.category?.toLowerCase().includes(query)
      );
    });
  }, [agentSearch, agents, selectedAgents]);

  const handleSelectAgent = (agent: Agent) => {
    setSelectedAgents((current) => [...current, agent]);
    setAgentSearch("");
    setAgentDropdownOpen(true);
  };

  const handleRemoveAgent = (agentId: string) => {
    setSelectedAgents((current) => current.filter((agent) => agent.id !== agentId));
  };

  const handleSave = () => {
    if (!name.trim()) {
      setNameError(true);
      return;
    }

    onSave({
      id: skill?.id ?? crypto.randomUUID(),
      name: name.trim(),
      description: description.trim(),
      instruction: instruction.trim(),
      agents: selectedAgents,
      createdAt: skill?.createdAt ?? new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
  };

  return (
    <div className="absolute inset-0 z-50 bg-zinc-950 font-sans text-zinc-100">
      <div className="flex h-dvh flex-col overflow-hidden bg-[#0b0b0c]">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-900/80 px-4 md:px-6">
          <button
            onClick={onClose}
            className="inline-flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-zinc-500 transition-colors hover:bg-zinc-900 hover:text-zinc-200"
          >
            <ArrowLeft size={15} />
            <span>Skills</span>
          </button>

          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-600 transition-colors hover:bg-zinc-900 hover:text-zinc-300"
            aria-label="Cerrar"
          >
            <X size={16} />
          </button>
        </header>

        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[760px] px-5 py-8 md:px-0 md:py-14">
            <div className="space-y-8">
              <section className="space-y-2">
                <input
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setNameError(false);
                  }}
                  placeholder="Nombre de la skill"
                  className="block w-full bg-transparent p-0 text-2xl font-semibold leading-tight text-zinc-100 placeholder:text-zinc-600 outline-none"
                />
                <input
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Agrega una descripcion opcional..."
                  className="block w-full bg-transparent p-0 text-sm leading-relaxed text-zinc-500 placeholder:text-zinc-600 outline-none"
                />
                {nameError && (
                  <p className="text-[11px] text-rose-400">El nombre es obligatorio.</p>
                )}
              </section>

              <section className="space-y-3">
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/55 transition-colors focus-within:border-zinc-600">
                  <textarea
                    value={instruction}
                    onChange={(e) => setInstruction(e.target.value)}
                    placeholder="Agrega instrucciones..."
                    className="min-h-[272px] w-full resize-none bg-transparent px-4 py-4 font-sans text-sm leading-relaxed text-zinc-100 placeholder:text-zinc-600 outline-none"
                  />
                </div>
                <div className="text-[10px] font-mono text-zinc-600">{instruction.length} chars</div>
              </section>

              <section className="space-y-3">
                <div>
                  <h3 className="text-sm font-semibold text-zinc-100">Agentes</h3>
                  <p className="mt-1 text-sm text-zinc-500">Asigna esta skill a uno o mas agentes.</p>
                </div>

                <div ref={dropdownRef} className="relative">
                  <div className="relative">
                    <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500" />
                    <input
                      type="text"
                      value={agentSearch}
                      onChange={(e) => {
                        setAgentSearch(e.target.value);
                        setAgentDropdownOpen(true);
                      }}
                      onFocus={() => setAgentDropdownOpen(true)}
                      placeholder="Agregar agentes"
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-950 py-2.5 pl-9 pr-4 text-sm text-zinc-100 placeholder:text-zinc-600 outline-none transition-colors hover:border-zinc-700 focus:border-zinc-600"
                    />
                  </div>

                  {agentDropdownOpen && (
                    <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-50 max-h-56 overflow-y-auto rounded-lg border border-zinc-800 bg-[#101011] py-1 shadow-2xl shadow-black/60">
                      {availableAgents.length === 0 ? (
                        <p className="px-3 py-3 text-center text-xs text-zinc-500">
                          No hay agentes disponibles
                        </p>
                      ) : (
                        availableAgents.map((agent) => (
                          <button
                            key={agent.id}
                            type="button"
                            onClick={() => handleSelectAgent(agent)}
                            className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-zinc-900"
                          >
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-zinc-800 bg-zinc-900">
                              <AgentVisualIcon agent={agent} size={15} />
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-medium text-zinc-200">{agent.name}</p>
                              <p className="truncate text-xs capitalize text-zinc-500">{agent.category ?? "general"}</p>
                            </div>
                            <UserPlus size={15} className="text-zinc-600" />
                          </button>
                        ))
                      )}
                    </div>
                  )}
                </div>

                {selectedAgents.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {selectedAgents.map((agent) => (
                      <div
                        key={agent.id}
                        className="group flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-900 px-2.5 py-1.5"
                      >
                        <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-zinc-950">
                          <AgentVisualIcon agent={agent} size={12} />
                        </div>
                        <span className="max-w-[180px] truncate text-xs font-medium text-zinc-300">
                          {agent.name}
                        </span>
                        <button
                          type="button"
                          onClick={() => handleRemoveAgent(agent.id)}
                          className="rounded-sm text-zinc-600 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
                          aria-label={`Quitar ${agent.name}`}
                        >
                          <X size={13} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  onClick={onClose}
                  className="rounded-full border border-zinc-800 bg-zinc-900 px-4 py-2 text-sm font-medium text-zinc-300 transition-colors hover:border-zinc-700 hover:bg-zinc-800 hover:text-zinc-100"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleSave}
                  className="rounded-full bg-zinc-100 px-5 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-white"
                >
                  {isEdit ? "Guardar cambios" : "Crear skill"}
                </button>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
