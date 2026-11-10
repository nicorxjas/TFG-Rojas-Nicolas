"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  ChevronDown,
  DollarSign,
  Loader2,
  Package,
  Plus,
  Search,
  Settings,
  ShoppingCart,
  TrendingDown,
  TrendingUp,
  Users,
  X,
} from "lucide-react";
import { Agent } from "@/app/agentes/types";
import { Skill } from "@/app/skills/types";
import {
  AGENT_ICON_COLORS,
  AGENT_ICON_OPTIONS,
  AgentVisualIcon,
  getAgentIconOption,
  getDefaultAgentIconName,
} from "./agent-icon";
import { CompactAgentEmojiPicker } from "./CompactAgentEmojiPicker";

interface AgentModalProps {
  agent?: Agent | null;
  skills: Skill[];
  onClose: () => void;
  onSave: (agent: Agent) => void;
}

const CATEGORIES = [
  { value: "stock", label: "Stock", icon: <Package size={14} />, color: "text-orange-400" },
  { value: "operaciones", label: "Operaciones", icon: <Settings size={14} />, color: "text-teal-400" },
  { value: "ventas", label: "Ventas", icon: <ShoppingCart size={14} />, color: "text-fuchsia-400" },
  { value: "clientes", label: "Clientes", icon: <Users size={14} />, color: "text-indigo-400" },
  { value: "finanzas", label: "Finanzas", icon: <DollarSign size={14} />, color: "text-emerald-400" },
  { value: "churn", label: "Churn", icon: <TrendingDown size={14} />, color: "text-rose-400" },
  { value: "oportunidad", label: "Oportunidad", icon: <TrendingUp size={14} />, color: "text-sky-400" },
  { value: "riesgos", label: "Riesgos", icon: <AlertTriangle size={14} />, color: "text-amber-400" },
  { value: "general", label: "General", icon: <Bot size={14} />, color: "text-violet-400" },
];

function formatSkillCount(count: number) {
  return `${count} skill${count === 1 ? "" : "s"}`;
}

function formatSkillUpdated(skill: Skill) {
  const source = skill.updatedAt ?? skill.createdAt;
  if (!source) return "Updated just now";

  const diffMinutes = Math.max(0, Math.floor((Date.now() - new Date(source).getTime()) / 60000));
  if (diffMinutes < 1) return "Updated just now";
  if (diffMinutes < 60) return `Updated ${diffMinutes}m ago`;

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
  }).format(new Date(source));
}

export function AgentModal({ agent, skills, onClose, onSave }: AgentModalProps) {
  const isEdit = !!agent;

  const [name, setName] = useState(agent?.name ?? "");
  const [description, setDescription] = useState(agent?.description ?? "");
  const [systemPrompt, setSystemPrompt] = useState(agent?.systemPrompt ?? "");
  const [category, setCategory] = useState(agent?.category ?? "general");
  const [iconType, setIconType] = useState<"icon" | "emoji">(agent?.iconType ?? "icon");
  const [iconName, setIconName] = useState(agent?.iconName ?? getDefaultAgentIconName(agent?.category ?? "general"));
  const [iconColor, setIconColor] = useState(agent?.iconColor ?? AGENT_ICON_COLORS[0]);
  const [iconEmoji, setIconEmoji] = useState(agent?.iconEmoji ?? "\u{1F916}");
  const [iconSearch, setIconSearch] = useState("");
  const [iconPickerOpen, setIconPickerOpen] = useState(false);
  const [iconPickerTab, setIconPickerTab] = useState<"icon" | "emoji">(agent?.iconType ?? "icon");
  const [catOpen, setCatOpen] = useState(false);
  const [nameError, setNameError] = useState(false);
  const [isImproving, setIsImproving] = useState(false);
  const [improveError, setImproveError] = useState<string | null>(null);
  const [selectedSkills, setSelectedSkills] = useState<Skill[]>(agent?.skills ?? []);
  const [skillSearch, setSkillSearch] = useState("");
  const [skillPickerOpen, setSkillPickerOpen] = useState(false);
  const iconPickerRef = useRef<HTMLDivElement>(null);
  const skillPickerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && iconPickerOpen) {
        setIconPickerOpen(false);
        return;
      }
      if (e.key === "Escape" && skillPickerOpen) {
        setSkillPickerOpen(false);
        return;
      }
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [iconPickerOpen, skillPickerOpen, onClose]);

  useEffect(() => {
    const onPointerDown = (e: MouseEvent) => {
      if (!iconPickerRef.current?.contains(e.target as Node)) {
        setIconPickerOpen(false);
      }
      if (!skillPickerRef.current?.contains(e.target as Node)) {
        setSkillPickerOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  const handleSave = () => {
    if (!name.trim()) {
      setNameError(true);
      return;
    }

    const saved: Agent = {
      id: agent?.id ?? crypto.randomUUID(),
      name: name.trim(),
      description: description.trim(),
      systemPrompt: systemPrompt.trim(),
      category,
      iconType,
      iconName,
      iconColor,
      iconEmoji,
      skills: selectedSkills,
      createdAt: agent?.createdAt ?? new Date().toISOString(),
    };

    onSave(saved);
  };

  const handleImprovePrompt = async () => {
    const raw = systemPrompt.trim();
    if (!raw) {
      setImproveError("Escribi instrucciones primero.");
      return;
    }

    setIsImproving(true);
    setImproveError(null);

    try {
      const res = await fetch("http://localhost:8000/chat/improve-prompt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          raw_description: raw,
          agent_name: name.trim(),
          category,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail ?? `Error ${res.status}`);
      }

      const data = await res.json();
      setSystemPrompt(data.improved_prompt ?? raw);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "No se pudo mejorar el prompt. Intenta de nuevo.";
      setImproveError(message);
    } finally {
      setIsImproving(false);
    }
  };

  const selectedCat = CATEGORIES.find((c) => c.value === category) ?? CATEGORIES[8];
  const availableSkills = useMemo(() => {
    const selectedIds = new Set(selectedSkills.map((skill) => skill.id));
    const query = skillSearch.trim().toLowerCase();

    return skills.filter((skill) => {
      if (selectedIds.has(skill.id)) return false;
      if (!query) return true;
      return (
        skill.name.toLowerCase().includes(query) ||
        skill.description.toLowerCase().includes(query)
      );
    });
  }, [skillSearch, selectedSkills, skills]);

  const handleSelectSkill = (skill: Skill) => {
    setSelectedSkills((current) => [...current, skill]);
    setSkillSearch("");
    setSkillPickerOpen(false);
  };

  const handleRemoveSkill = (skillId: string) => {
    setSelectedSkills((current) => current.filter((skill) => skill.id !== skillId));
  };

  const filteredIconOptions = AGENT_ICON_OPTIONS.filter((option) => {
    const query = iconSearch.trim().toLowerCase();
    if (!query) return true;
    return [
      option.name,
      option.label,
      ...option.keywords,
    ].some((value) => value.toLowerCase().includes(query));
  });

  return (
    <div className="absolute inset-0 z-50 bg-[#f6f7f9] font-sans text-zinc-950 dark:bg-zinc-950 dark:text-zinc-100">
      <div className="flex h-dvh flex-col overflow-hidden bg-[#f6f7f9] dark:bg-[#0b0b0c]">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-200/80 px-4 md:px-6 dark:border-zinc-900/80">
          <button
            onClick={onClose}
            className="inline-flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-zinc-950 dark:text-zinc-500 dark:hover:bg-zinc-900 dark:hover:text-zinc-200"
          >
            <ArrowLeft size={15} />
            <span>Agentes</span>
          </button>

          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-950 dark:text-zinc-600 dark:hover:bg-zinc-900 dark:hover:text-zinc-300"
            aria-label="Cerrar"
          >
            <X size={16} />
          </button>
        </header>

        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[760px] px-5 py-8 md:px-0 md:py-14">
            <div className="space-y-8">
              <section className="flex items-start gap-3.5">
                <div ref={iconPickerRef} className="relative mt-0.5 shrink-0">
                  <button
                    type="button"
                    onClick={() => {
                      setIconPickerOpen((open) => !open);
                      setCatOpen(false);
                    }}
                    className={`flex h-8 w-8 items-center justify-center rounded-md border bg-white/90 text-zinc-500 shadow-sm shadow-zinc-200/60 transition-colors hover:border-zinc-300 hover:bg-zinc-50 hover:text-zinc-950 dark:bg-zinc-800/80 dark:text-zinc-400 dark:shadow-none dark:hover:border-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-100 ${
                      iconPickerOpen ? "border-zinc-300 bg-zinc-50 text-zinc-950 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100" : "border-zinc-200 dark:border-zinc-700"
                    }`}
                    aria-label="Personalizar icono del agente"
                    aria-expanded={iconPickerOpen}
                  >
                    <AgentVisualIcon
                      agent={{ category, iconType, iconName, iconColor, iconEmoji }}
                      size={17}
                    />
                  </button>

                  {iconPickerOpen && (
                    <div className="absolute left-0 top-full z-50 mt-2 w-[410px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-2xl shadow-zinc-200/80 dark:border-zinc-800 dark:bg-[#18181a] dark:shadow-black/50">
                      <div className="flex border-b border-zinc-200 dark:border-zinc-800">
                        <button
                          type="button"
                          onClick={() => setIconPickerTab("icon")}
                          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
                            iconPickerTab === "icon"
                              ? "border-b border-indigo-500 text-zinc-950 dark:border-indigo-400 dark:text-zinc-100"
                              : "text-zinc-500 hover:text-zinc-950 dark:hover:text-zinc-200"
                          }`}
                        >
                          Icons
                        </button>
                        <button
                          type="button"
                          onClick={() => setIconPickerTab("emoji")}
                          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
                            iconPickerTab === "emoji"
                              ? "border-b border-indigo-500 text-zinc-950 dark:border-indigo-400 dark:text-zinc-100"
                              : "text-zinc-500 hover:text-zinc-950 dark:hover:text-zinc-200"
                          }`}
                        >
                          Emojis
                        </button>
                      </div>

                      {iconPickerTab === "icon" ? (
                        <div className="p-3">
                          <div className="mb-3 flex items-center gap-2 border-b border-zinc-200 pb-3 dark:border-zinc-800">
                            {AGENT_ICON_COLORS.map((color) => (
                              <button
                                key={color}
                                type="button"
                                onClick={() => {
                                  setIconType("icon");
                                  setIconColor(color);
                                }}
                                className={`flex h-6 w-6 items-center justify-center rounded-full transition-transform hover:scale-110 ${
                                  iconColor === color ? "ring-2 ring-zinc-900/20 ring-offset-2 ring-offset-white dark:ring-zinc-200 dark:ring-offset-[#18181a]" : ""
                                }`}
                                style={{ backgroundColor: color }}
                                aria-label={`Color ${color}`}
                              >
                                {iconColor === color && <span className="h-2 w-2 rounded-full bg-white/85 dark:bg-zinc-950/70" />}
                              </button>
                            ))}
                          </div>

                          <input
                            value={iconSearch}
                            onChange={(e) => setIconSearch(e.target.value)}
                            placeholder="Search icons..."
                            className="mb-3 w-full bg-transparent px-1 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 outline-none dark:text-zinc-200 dark:placeholder:text-zinc-600"
                          />

                          <div className="grid max-h-[280px] grid-cols-10 gap-1 overflow-y-auto pr-1">
                            {filteredIconOptions.map((option) => {
                              const Icon = option.icon;
                              const active = iconType === "icon" && getAgentIconOption(iconName).name === option.name;
                              return (
                                <button
                                  key={option.name}
                                  type="button"
                                  onClick={() => {
                                    setIconType("icon");
                                    setIconName(option.name);
                                  }}
                                  className={`flex h-8 w-8 items-center justify-center rounded-md transition-colors ${
                                    active ? "bg-[#f1f2f4] dark:bg-zinc-700" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-950 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
                                  }`}
                                  title={option.label}
                                >
                                  <Icon size={16} strokeWidth={2} style={{ color: iconColor }} />
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ) : (
                        <div className="p-2">
                          <CompactAgentEmojiPicker
                            searchPlaceholder="Search emoji..."
                            onEmojiClick={(emojiData) => {
                              setIconType("emoji");
                              setIconEmoji(emojiData.emoji);
                            }}
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="min-w-0 flex-1">
                  <input
                    value={name}
                    onChange={(e) => {
                      setName(e.target.value);
                      setNameError(false);
                    }}
                    placeholder="Nombre de Agente"
                    className="block w-full bg-transparent p-0 text-2xl font-semibold leading-tight text-zinc-950 placeholder:text-zinc-400 outline-none dark:text-zinc-100 dark:placeholder:text-zinc-600"
                  />
                  <input
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Agrega una descripcion opcional..."
                    className="mt-2 block w-full bg-transparent p-0 text-sm leading-relaxed text-zinc-500 placeholder:text-zinc-400 outline-none dark:text-zinc-500 dark:placeholder:text-zinc-600"
                  />
                  {nameError && (
                    <p className="mt-2 text-[11px] text-rose-400">El nombre es obligatorio.</p>
                  )}
                </div>
              </section>

              <section className="space-y-3">
                <div>
                  <h3 className="text-sm font-semibold text-zinc-950 dark:text-zinc-100">Instrucciones</h3>
                </div>

                <div className="relative rounded-xl border border-zinc-200 bg-white/70 shadow-sm shadow-zinc-200/50 transition-colors focus-within:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-900/55 dark:shadow-none dark:focus-within:border-zinc-600">
                  <textarea
                    value={systemPrompt}
                    onChange={(e) => {
                      setSystemPrompt(e.target.value);
                      setImproveError(null);
                    }}
                    placeholder="Detalla instrucciones..."
                    className="min-h-[220px] w-full resize-none bg-transparent px-4 pb-16 pt-4 font-sans text-sm leading-relaxed text-zinc-950 placeholder:text-zinc-400 outline-none dark:text-zinc-100 dark:placeholder:text-zinc-600"
                  />

                  <button
                    id="improve-prompt-btn"
                    type="button"
                    onClick={handleImprovePrompt}
                    disabled={isImproving}
                    className={`absolute bottom-3 right-3 inline-flex h-8 items-center justify-center rounded-md border px-3 text-xs font-medium shadow-lg shadow-zinc-200/80 transition-colors dark:shadow-black/20 ${
                      isImproving
                        ? "cursor-not-allowed border-zinc-200 bg-[#f3f4f6] text-zinc-400 dark:border-zinc-800 dark:bg-zinc-950/90 dark:text-zinc-500"
                        : "border-zinc-200 bg-white text-zinc-700 hover:border-zinc-300 hover:bg-zinc-50 hover:text-zinc-950 dark:border-zinc-700/80 dark:bg-[#111113] dark:text-zinc-300 dark:hover:border-zinc-600 dark:hover:bg-zinc-900 dark:hover:text-zinc-100"
                    }`}
                  >
                    {isImproving ? (
                      <span className="inline-flex items-center gap-2">
                        <Loader2 size={12} className="animate-spin text-zinc-400 dark:text-zinc-500" />
                        Mejorando...
                      </span>
                    ) : (
                      "Mejorar con IA"
                    )}
                  </button>
                </div>

                <div className="space-y-1">
                  <div className="text-[10px] font-mono text-zinc-400 dark:text-zinc-600">{systemPrompt.length} chars</div>
                  {improveError && (
                    <p className="text-[11px] leading-relaxed text-rose-400">
                      {improveError}
                    </p>
                  )}
                </div>
              </section>

              <section className="space-y-3">
                <div>
                  <h3 className="text-sm font-semibold text-zinc-950 dark:text-zinc-100">Categoría del agente</h3>
                </div>

                <div className="rounded-xl border border-zinc-200 bg-white/70 p-3 shadow-sm shadow-zinc-200/50 dark:border-zinc-800 dark:bg-zinc-900/55 dark:shadow-none">
                  <div className="relative">
                    <button
                      onClick={() => setCatOpen((v) => !v)}
                      className={`w-full flex items-center gap-2 rounded-lg border bg-white px-3 py-2.5 text-left text-sm transition-colors hover:bg-zinc-50 dark:bg-zinc-950 dark:hover:bg-zinc-900
                        ${catOpen ? "border-zinc-300 dark:border-zinc-600" : "border-zinc-200 dark:border-zinc-800"}`}
                    >
                      <span className={selectedCat.color}>{selectedCat.icon}</span>
                      <span className="flex-1 text-zinc-800 capitalize dark:text-zinc-200">{selectedCat.label}</span>
                      <ChevronDown
                        size={14}
                        className={`text-zinc-400 transition-transform dark:text-zinc-500 ${catOpen ? "rotate-180" : ""}`}
                      />
                    </button>

                    {catOpen && (
                      <div className="absolute top-full mt-1 left-0 right-0 z-20 overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-xl shadow-zinc-200/70 dark:border-zinc-800 dark:bg-zinc-900 dark:shadow-none">
                        {CATEGORIES.map((cat) => (
                          <button
                            key={cat.value}
                            onClick={() => {
                              setCategory(cat.value);
                              setCatOpen(false);
                            }}
                            className={`w-full flex items-center gap-2.5 px-3 py-2.5 text-left text-sm transition-colors
                              ${category === cat.value
                                ? "bg-[#f1f2f4] text-zinc-950 dark:bg-zinc-800 dark:text-zinc-100"
                                : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-950 dark:text-zinc-400 dark:hover:bg-zinc-800/60 dark:hover:text-zinc-200"
                              }`}
                          >
                            <span className={cat.color}>{cat.icon}</span>
                            <span>{cat.label}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </section>

              <section className="space-y-3">
                <div>
                  <h3 className="text-sm font-semibold text-zinc-950 dark:text-zinc-100">Skills</h3>
                  <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-500">
                    Prompts reutilizables que el agente puede seleccionar automaticamente o invocar con comandos slash.
                  </p>
                </div>

                <div className="rounded-xl border border-zinc-200 bg-white/65 shadow-sm shadow-zinc-200/50 dark:border-zinc-800 dark:bg-zinc-900/45 dark:shadow-none">
                  <div className="flex h-[58px] items-center justify-between border-b border-zinc-200/80 px-4 dark:border-zinc-800/80">
                    <span className="text-sm font-semibold text-zinc-950 dark:text-zinc-100">
                      {formatSkillCount(selectedSkills.length)}
                    </span>

                    <div ref={skillPickerRef} className="relative">
                      <button
                        type="button"
                        onClick={() => setSkillPickerOpen((open) => !open)}
                        className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-950 dark:text-zinc-500 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
                        aria-label="Agregar skill"
                        aria-expanded={skillPickerOpen}
                      >
                        <Plus size={16} />
                      </button>

                      {skillPickerOpen && (
                        <div className="absolute right-0 top-full z-50 mt-2 w-[320px] overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-2xl shadow-zinc-200/80 dark:border-zinc-800 dark:bg-[#101011] dark:shadow-black/60">
                          <div className="border-b border-zinc-200 p-2 dark:border-zinc-800">
                            <div className="relative">
                              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400 dark:text-zinc-600" />
                              <input
                                value={skillSearch}
                                onChange={(e) => setSkillSearch(e.target.value)}
                                placeholder="Buscar skill..."
                                className="h-9 w-full rounded-md border border-zinc-200 bg-zinc-50 pl-8 pr-3 text-sm text-zinc-950 outline-none placeholder:text-zinc-400 focus:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-200 dark:placeholder:text-zinc-600 dark:focus:border-zinc-600"
                              />
                            </div>
                          </div>

                          <div className="max-h-56 overflow-y-auto py-1">
                            {availableSkills.length === 0 ? (
                              <p className="px-3 py-3 text-center text-xs text-zinc-500">
                                No hay skills disponibles
                              </p>
                            ) : (
                              availableSkills.map((skill) => (
                                <button
                                  key={skill.id}
                                  type="button"
                                  onClick={() => handleSelectSkill(skill)}
                                  className="flex w-full flex-col gap-0.5 px-3 py-2.5 text-left transition-colors hover:bg-zinc-100 dark:hover:bg-zinc-900"
                                >
                                  <span className="truncate text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                                    {skill.name}
                                  </span>
                                  <span className="truncate text-xs text-zinc-500 dark:text-zinc-500">
                                    {skill.description || "Sin descripcion"}
                                  </span>
                                </button>
                              ))
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {selectedSkills.length === 0 ? (
                    <div className="px-4 py-5 text-sm text-zinc-500 dark:text-zinc-500">
                      Sin skills asignadas
                    </div>
                  ) : (
                    <div className="divide-y divide-zinc-200/80 dark:divide-zinc-800/70">
                      {selectedSkills.map((skill) => (
                        <div
                          key={skill.id}
                          className="group flex items-center justify-between gap-3 px-4 py-4"
                        >
                          <div className="min-w-0">
                            <h4 className="truncate text-sm font-semibold text-zinc-950 dark:text-zinc-100">
                              {skill.name}
                            </h4>
                            <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-500">
                              {formatSkillUpdated(skill)}
                            </p>
                          </div>

                          <button
                            type="button"
                            onClick={() => handleRemoveSkill(skill.id)}
                            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-zinc-400 opacity-0 transition-all hover:bg-zinc-100 hover:text-zinc-700 group-hover:opacity-100 dark:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
                            aria-label={`Quitar ${skill.name}`}
                          >
                            <X size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </section>

              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  onClick={onClose}
                  className="rounded-full border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:border-zinc-300 hover:bg-zinc-50 hover:text-zinc-950 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:border-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleSave}
                  className="rounded-full bg-black px-5 py-2 text-sm font-semibold text-[#ffffff] transition-colors hover:bg-[#24262b] dark:bg-zinc-100 dark:text-zinc-950 dark:hover:bg-white"
                >
                  {isEdit ? "Guardar cambios" : "Crear agente"}
                </button>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
