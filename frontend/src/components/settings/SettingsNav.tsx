"use client";

import { ArrowLeft, Building2, FolderTree, Palette, Plug, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const settingsItems = [
  { href: "/settings/preferencias", label: "Preferencias", icon: Palette },
  { href: "/settings", label: "Perfil", icon: UserRound },
  { href: "/settings/empresa", label: "Empresa", icon: Building2 },
  { href: "/settings/categorias", label: "Categorías", icon: FolderTree },
  { href: "/settings/conectores", label: "Conectores", icon: Plug },
];

export function SettingsNav() {
  const pathname = usePathname();
  const handleBackToApp = () => {
    window.location.assign("/dashboard");
  };

  return (
    <aside className="flex w-full shrink-0 flex-col border-b border-zinc-800 bg-zinc-900 px-3 py-3 text-sm font-medium text-zinc-300 md:h-full md:w-[280px] md:border-b-0 md:border-r md:py-4">
      <button
        type="button"
        onClick={handleBackToApp}
        className="mb-3 flex h-10 w-full items-center gap-3 rounded-lg px-3 text-left text-zinc-300 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
      >
        <ArrowLeft size={18} className="shrink-0 opacity-70" />
        <span>Volver a la app</span>
      </button>

      <div className="mb-3 h-px bg-zinc-800/50" />

      <nav className="grid grid-cols-2 gap-1 md:flex md:flex-col">
        {settingsItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
                active
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100"
              }`}
            >
              <Icon size={18} className="shrink-0 opacity-70" />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
