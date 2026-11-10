"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, CheckCircle2, Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { AgentVisualIcon, AGENT_ICON_COLORS, AGENT_ICON_OPTIONS } from "@/components/agentes/agent-icon";
import { CompactAgentEmojiPicker } from "@/components/agentes/CompactAgentEmojiPicker";

type CategoryRow = {
  id: string;
  name: string;
  slug: string | null;
  icon_type: "icon" | "emoji" | null;
  icon_name: string | null;
  icon_color: string | null;
  icon_emoji: string | null;
  created_at: string | null;
};

type CategoryDraft = {
  id?: string;
  name: string;
  iconType: "icon" | "emoji";
  iconName: string;
  iconColor: string;
  iconEmoji: string;
};

type ToastState = {
  id: number;
  message: string;
};

function mapRowToDraft(category?: CategoryRow | null): CategoryDraft {
  return {
    id: category?.id,
    name: category?.name ?? "",
    iconType: category?.icon_type ?? "icon",
    iconName: category?.icon_name ?? "tags",
    iconColor: category?.icon_color ?? AGENT_ICON_COLORS[0],
    iconEmoji: category?.icon_emoji ?? "🏷️",
  };
}

function slugify(value: string) {
  return value
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function categoryIconProps(category: Pick<CategoryRow, "icon_type" | "icon_name" | "icon_color" | "icon_emoji">) {
  return {
    category: "general",
    iconType: category.icon_type ?? "icon",
    iconName: category.icon_name ?? "tags",
    iconColor: category.icon_color ?? AGENT_ICON_COLORS[0],
    iconEmoji: category.icon_emoji ?? undefined,
  };
}

export default function CategoriasSettingsPage() {
  const supabase = createClient();
  const [categories, setCategories] = useState<CategoryRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [editingCategory, setEditingCategory] = useState<CategoryRow | null>(null);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);

  const readCategories = useCallback(() => {
    return supabase
      .from("categories")
      .select("id, name, slug, icon_type, icon_name, icon_color, icon_emoji, created_at")
      .order("name", { ascending: true });
  }, [supabase]);

  const refreshCategories = async () => {
    setIsLoading(true);
    setMessage(null);
    const { data, error } = await readCategories();
    if (error) {
      setMessage(`No se pudieron cargar las categorías: ${error.message}`);
      setCategories([]);
    } else {
      setCategories((data ?? []) as CategoryRow[]);
    }

    setIsLoading(false);
  };

  useEffect(() => {
    let cancelled = false;

    const loadInitialCategories = async () => {
      const { data, error } = await readCategories();
      if (cancelled) return;

      if (error) {
        setMessage(`No se pudieron cargar las categorías: ${error.message}`);
        setCategories([]);
      } else {
        setCategories((data ?? []) as CategoryRow[]);
      }

      setIsLoading(false);
    };

    void loadInitialCategories();

    return () => {
      cancelled = true;
    };
  }, [readCategories]);

  useEffect(() => {
    if (!toast) return;

    const timeout = window.setTimeout(() => {
      setToast(null);
    }, 2600);

    return () => window.clearTimeout(timeout);
  }, [toast]);

  const handleCreate = () => {
    setEditingCategory(null);
    setIsEditorOpen(true);
  };

  const handleEdit = (category: CategoryRow) => {
    setEditingCategory(category);
    setIsEditorOpen(true);
  };

  const handleSave = async (draft: CategoryDraft) => {
    const cleanName = draft.name.trim();
    if (!cleanName) {
      setMessage("El nombre de la categoría es obligatorio.");
      return;
    }

    setIsSaving(true);
    setMessage(null);

    const payload = {
      name: cleanName,
      slug: slugify(cleanName),
      icon_type: draft.iconType,
      icon_name: draft.iconType === "icon" ? draft.iconName : "tags",
      icon_color: draft.iconColor,
      icon_emoji: draft.iconType === "emoji" ? draft.iconEmoji : null,
    };

    const query = draft.id
      ? supabase.from("categories").update(payload).eq("id", draft.id)
      : supabase.from("categories").insert(payload);

    const { error } = await query;
    setIsSaving(false);

    if (error) {
      setMessage(`No se pudo guardar la categoría: ${error.message}`);
      return;
    }

    setIsEditorOpen(false);
    setEditingCategory(null);
    await refreshCategories();
  };

  const handleDelete = async (category: CategoryRow) => {
    setMessage(null);
    const { error } = await supabase.from("categories").delete().eq("id", category.id);

    if (error) {
      setMessage(`No se pudo eliminar la categoría: ${error.message}`);
      return;
    }

    await refreshCategories();
    setToast((current) => ({ id: (current?.id ?? 0) + 1, message: "Categoría eliminada" }));
  };

  return (
    <>
      <section className="flex-1 overflow-y-auto bg-[#0a0a0b]">
        <div className="mx-auto w-full max-w-[760px] px-5 py-10 md:py-16">
          <h1 className="mb-2 text-2xl font-semibold text-zinc-50">Categorías</h1>
          <p className="mb-8 text-sm text-zinc-500">Administra el maestro de categorías disponible en la plataforma.</p>

          <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/45">
            <button
              onClick={handleCreate}
              className="flex min-h-[64px] w-full items-center gap-3 border-b border-zinc-800 px-4 text-left transition-colors hover:bg-zinc-900"
            >
              <span className="flex size-8 items-center justify-center rounded-md bg-zinc-800 text-zinc-300">
                <Plus size={16} />
              </span>
              <span className="text-sm font-semibold text-zinc-100">Crear nueva categoría</span>
            </button>

            {isLoading ? (
              <div className="px-4 py-8 text-sm text-zinc-500">Cargando categorías...</div>
            ) : categories.length === 0 ? (
              <div className="px-4 py-8 text-sm text-zinc-500">Todavía no hay categorías.</div>
            ) : (
              categories.map((category) => (
                <div
                  key={category.id}
                  className="flex min-h-[64px] items-center gap-3 border-b border-zinc-800 px-4 last:border-b-0"
                >
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-zinc-800">
                    <AgentVisualIcon agent={categoryIconProps(category)} size={17} />
                  </span>

                  <button
                    onClick={() => handleEdit(category)}
                    className="min-w-0 flex-1 text-left text-sm font-semibold text-zinc-100 transition-colors hover:text-white"
                  >
                    <span className="block truncate">{category.name}</span>
                  </button>

                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handleEdit(category)}
                      className="flex size-8 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
                      aria-label={`Editar ${category.name}`}
                    >
                      <Pencil size={15} />
                    </button>
                    <button
                      onClick={() => handleDelete(category)}
                      className="flex size-8 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-rose-300"
                      aria-label={`Eliminar ${category.name}`}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>

          {message && (
            <p className={`mt-4 text-sm ${message.startsWith("No se") ? "text-rose-400" : "text-zinc-500"}`}>
              {message}
            </p>
          )}
        </div>
      </section>

      {isEditorOpen && (
        <CategoryEditorModal
          category={editingCategory}
          isSaving={isSaving}
          onClose={() => {
            setIsEditorOpen(false);
            setEditingCategory(null);
          }}
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
    </>
  );
}

function CategoryEditorModal({
  category,
  isSaving,
  onClose,
  onSave,
}: {
  category: CategoryRow | null;
  isSaving: boolean;
  onClose: () => void;
  onSave: (draft: CategoryDraft) => void;
}) {
  const [draft, setDraft] = useState<CategoryDraft>(() => mapRowToDraft(category));
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const [iconTab, setIconTab] = useState<"icons" | "emojis">("icons");
  const [iconSearch, setIconSearch] = useState("");
  const pickerRef = useRef<HTMLDivElement>(null);
  const iconButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (pickerRef.current?.contains(target) || iconButtonRef.current?.contains(target)) return;
      setIsPickerOpen(false);
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, []);

  const filteredIcons = useMemo(() => {
    const query = iconSearch.trim().toLowerCase();
    if (!query) return AGENT_ICON_OPTIONS;

    return AGENT_ICON_OPTIONS.filter((option) =>
      [option.name, option.label, ...option.keywords].some((value) => value.toLowerCase().includes(query)),
    );
  }, [iconSearch]);

  const previewIcon = {
    category: "general",
    iconType: draft.iconType,
    iconName: draft.iconName,
    iconColor: draft.iconColor,
    iconEmoji: draft.iconEmoji,
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm">
      <div className="w-full max-w-[520px] rounded-xl border border-zinc-800 bg-[#111113] shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
          <h2 className="text-base font-semibold text-zinc-50">
            {category ? "Editar categoría" : "Nueva categoría"}
          </h2>
          <button
            onClick={onClose}
            className="flex size-8 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
            aria-label="Cerrar"
          >
            <X size={17} />
          </button>
        </div>

        <div className="space-y-5 px-5 py-5">
          <div className="relative flex items-center gap-3">
            <button
              ref={iconButtonRef}
              onClick={() => setIsPickerOpen((open) => !open)}
              className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-zinc-700 bg-zinc-900 text-zinc-200 transition-colors hover:border-zinc-600 hover:bg-zinc-800"
              aria-label="Personalizar icono"
            >
              <AgentVisualIcon agent={previewIcon} size={20} />
            </button>

            <input
              value={draft.name}
              onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
              placeholder="Nombre de la categoría"
              className="h-10 min-w-0 flex-1 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm font-semibold text-zinc-100 outline-none transition-colors placeholder:text-zinc-600 focus:border-zinc-600"
              autoFocus
            />

            {isPickerOpen && (
              <div
                ref={pickerRef}
                className="absolute left-0 top-12 z-[90] w-[410px] overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
              >
                <div className="flex border-b border-zinc-800 px-3 pt-2">
                  <button
                    onClick={() => setIconTab("icons")}
                    className={`border-b px-3 py-2 text-sm font-semibold transition-colors ${
                      iconTab === "icons"
                        ? "border-indigo-400 text-zinc-100"
                        : "border-transparent text-zinc-500 hover:text-zinc-200"
                    }`}
                  >
                    Icons
                  </button>
                  <button
                    onClick={() => setIconTab("emojis")}
                    className={`border-b px-3 py-2 text-sm font-semibold transition-colors ${
                      iconTab === "emojis"
                        ? "border-indigo-400 text-zinc-100"
                        : "border-transparent text-zinc-500 hover:text-zinc-200"
                    }`}
                  >
                    Emojis
                  </button>
                </div>

                {iconTab === "icons" ? (
                  <div className="p-3">
                    <div className="mb-3 flex h-9 items-center gap-2 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-zinc-500 focus-within:border-zinc-600">
                      <Search size={15} />
                      <input
                        value={iconSearch}
                        onChange={(event) => setIconSearch(event.target.value)}
                        placeholder="Buscar icono..."
                        className="h-full flex-1 bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
                      />
                    </div>

                    <div className="mb-3 flex items-center gap-2">
                      {AGENT_ICON_COLORS.map((color) => (
                        <button
                          key={color}
                          onClick={() => setDraft((current) => ({ ...current, iconColor: color }))}
                          className="flex size-6 items-center justify-center rounded-full"
                          style={{ backgroundColor: color }}
                          aria-label={`Color ${color}`}
                        >
                          {draft.iconColor === color && <Check size={14} className="text-zinc-950" strokeWidth={3} />}
                        </button>
                      ))}
                    </div>

                    <div className="grid max-h-[250px] grid-cols-9 gap-1 overflow-y-auto pr-1">
                      {filteredIcons.map((option) => (
                        <button
                          key={option.name}
                          onClick={() => {
                            setDraft((current) => ({
                              ...current,
                              iconType: "icon",
                              iconName: option.name,
                            }));
                          }}
                          className={`flex size-8 items-center justify-center rounded-md transition-colors ${
                            draft.iconType === "icon" && draft.iconName === option.name
                              ? "bg-zinc-700 text-zinc-100"
                              : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
                          }`}
                          title={option.label}
                        >
                          <option.icon size={17} style={{ color: draft.iconColor }} />
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="p-2">
                    <CompactAgentEmojiPicker
                      searchPlaceholder="Buscar emoji..."
                      onEmojiClick={(emoji) => {
                        setDraft((current) => ({
                          ...current,
                          iconType: "emoji",
                          iconEmoji: emoji.emoji,
                        }));
                      }}
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-zinc-800 px-5 py-4">
          <button
            onClick={onClose}
            className="rounded-full border border-zinc-800 bg-zinc-900 px-4 py-2 text-sm font-semibold text-zinc-100 transition-colors hover:bg-zinc-800"
          >
            Cancelar
          </button>
          <button
            onClick={() => onSave(draft)}
            disabled={isSaving}
            className="rounded-full bg-zinc-100 px-4 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSaving ? "Guardando..." : category ? "Guardar cambios" : "Crear categoría"}
          </button>
        </div>
      </div>
    </div>
  );
}
