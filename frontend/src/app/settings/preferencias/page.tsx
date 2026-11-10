"use client";

import { Check, Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "@/components/theme/ThemeProvider";
import type { ThemePreference } from "@/lib/theme";

type ThemeOption = {
  value: ThemePreference;
  title: string;
  description: string;
  icon: typeof Monitor;
};

const themeOptions: ThemeOption[] = [
  {
    value: "system",
    title: "Preferencia del sistema",
    description: "Hereda automaticamente el tema claro u oscuro configurado en tu dispositivo.",
    icon: Monitor,
  },
  {
    value: "light",
    title: "Tema claro",
    description: "Superficies limpias, bordes sutiles y contraste suave con estetica Linear.",
    icon: Sun,
  },
  {
    value: "dark",
    title: "Tema oscuro",
    description: "Mantiene la experiencia oscura actual, sobria y de alto contraste.",
    icon: Moon,
  },
];

export default function PreferenciasSettingsPage() {
  const { preference, resolvedTheme, setPreference } = useTheme();
  const resolvedLabel = resolvedTheme === "dark" ? "Tema oscuro" : "Tema claro";

  return (
    <section className="flex-1 overflow-y-auto bg-[#0a0a0b]">
      <div className="mx-auto w-full max-w-[760px] px-5 py-10 md:py-16">
        <h1 className="mb-2 text-2xl font-semibold text-zinc-50">Preferencias</h1>
        <p className="mb-8 text-sm text-zinc-500">
          Ajusta la apariencia de Synthesis para trabajar con el modo que te resulte mas natural.
        </p>

        <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/45">
          {themeOptions.map(({ value, title, description, icon: Icon }) => {
            const active = preference === value;

            return (
              <button
                key={value}
                type="button"
                onClick={() => setPreference(value)}
                className={`grid min-h-[76px] w-full grid-cols-[auto_1fr_auto] items-center gap-4 border-b border-zinc-800 px-4 text-left transition-colors last:border-b-0 ${
                  active ? "bg-zinc-900/70" : "hover:bg-zinc-900/55"
                }`}
                role="radio"
                aria-checked={active}
              >
                <span
                  className={`flex size-9 items-center justify-center rounded-lg border transition-colors ${
                    active
                      ? "border-zinc-600 bg-zinc-100 text-zinc-950"
                      : "border-zinc-800 bg-zinc-950 text-zinc-500"
                  }`}
                >
                  <Icon size={17} />
                </span>

                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-zinc-100">{title}</span>
                  <span className="mt-1 block text-sm leading-5 text-zinc-500">{description}</span>
                </span>

                <span
                  className={`flex size-5 items-center justify-center rounded-full border transition-colors ${
                    active
                      ? "border-zinc-100 bg-zinc-100 text-zinc-950"
                      : "border-zinc-700 text-transparent"
                  }`}
                >
                  <Check size={13} strokeWidth={3} />
                </span>
              </button>
            );
          })}
        </div>

        <div className="mt-8 rounded-xl border border-zinc-800 bg-zinc-900/45 px-4 py-4">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-sm font-semibold text-zinc-100">Tema activo</h2>
              <p className="mt-1 text-sm text-zinc-500">
                {preference === "system"
                  ? `El sistema esta usando: ${resolvedLabel}.`
                  : `Synthesis esta usando: ${resolvedLabel}.`}
              </p>
            </div>

            <span className="mt-3 inline-flex h-7 items-center rounded-full border border-zinc-800 px-3 text-xs font-semibold text-zinc-400 sm:mt-0">
              {resolvedLabel}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
