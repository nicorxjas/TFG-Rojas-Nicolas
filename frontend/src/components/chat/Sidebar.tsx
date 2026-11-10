"use client";

import { useState, useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { useSidebarStore } from "@/lib/store";
import { NEW_CHAT_EVENT } from "@/lib/chat-events";
import {
  Search,
  MessageSquarePlus,
  ChevronDown,
  HelpCircle,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
  FileText,
  MessageSquare,
  Cpu,
  Network,
  Sparkles
} from "lucide-react";

export default function Sidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const supabase = createClient();
  const { isOpen, toggleSidebar } = useSidebarStore();
  const [userEmail, setUserEmail] = useState<string | null>("user@nyro.com");
  const [userInitial, setUserInitial] = useState<string>("U");
  const [isProfileOpen, setIsProfileOpen] = useState(false);

  useEffect(() => {
    async function getUser() {
      const { data: { user } } = await supabase.auth.getUser();
      if (user?.email) {
        setUserEmail(user.email);
        setUserInitial(user.email.charAt(0).toUpperCase());
      }
    }
    getUser();
  }, [supabase]);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.push("/login");
  };

  const handleNewChat = () => {
    window.dispatchEvent(new Event(NEW_CHAT_EVENT));
    if (pathname !== "/dashboard") router.push("/dashboard");
  };

  const navItems = [
    { href: "/dashboard", label: "Chat", icon: MessageSquare, active: pathname === "/dashboard" },
    { href: "/informes", label: "Informes", icon: FileText, active: pathname?.startsWith("/informes") },
    { href: "/agentes", label: "Agentes", icon: Cpu, active: pathname?.startsWith("/agentes") },
    { href: "/skills", label: "Skills", icon: Sparkles, active: pathname?.startsWith("/skills") },
    { href: "/modelo-semantico", label: "Modelo", icon: Network, active: pathname?.startsWith("/modelo-semantico") },
  ];

  return (
    <>
    <aside className={`${isOpen ? "w-[256px]" : "w-[72px]"} relative hidden h-full shrink-0 flex-col bg-black px-3 py-4 text-sm font-medium text-[#E0E0E0] transition-all duration-300 ease-in-out md:flex`}>
      <div className={`flex h-12 w-full items-center overflow-hidden whitespace-nowrap transition-all duration-300 ${isOpen ? "justify-between px-1" : "justify-center px-0"}`}>
        <div className={`flex items-center shrink-0 transition-all duration-300 ${isOpen ? "w-auto" : "justify-center"}`}>
          <button
            onClick={toggleSidebar}
            aria-label={isOpen ? "Contraer navegacion" : "Expandir navegacion"}
            className={`flex h-10 items-center rounded-full text-[#dfe7df] transition-colors hover:bg-white/10 hover:text-[#f7f7f2] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f7f7f2]/70 focus-visible:ring-offset-2 focus-visible:ring-offset-black ${isOpen ? "gap-3 px-2 pr-3" : "w-10 justify-center"}`}
          >
            {isOpen ? <PanelLeftClose size={20} /> : <PanelLeftOpen size={20} />}
            {isOpen && <span className="text-sm font-semibold tracking-tight">BI AI</span>}
          </button>
        </div>
        <div className={`flex items-center justify-end overflow-hidden transition-all duration-300 ${isOpen ? "opacity-100" : "w-0 opacity-0 invisible"}`}>
          <button
            aria-label="Buscar"
            className="flex h-10 w-10 items-center justify-center rounded-full text-[#aeb9b0] transition-colors hover:bg-white/10 hover:text-[#f7f7f2] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f7f7f2]/70 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
          >
            <Search size={20} />
          </button>
        </div>
      </div>

      {/* New Chat Button */}
      <div className={`pt-4 transition-all duration-300 ${isOpen ? "px-1 pb-4" : "px-0 pb-4"}`}>
        <button type="button" onClick={handleNewChat} aria-label="Nuevo chat" className={`mx-auto flex items-center overflow-hidden whitespace-nowrap text-[#f7f7f2] transition-all duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f7f7f2]/70 focus-visible:ring-offset-2 focus-visible:ring-offset-black ${isOpen ? "h-11 w-full rounded-full bg-white/10 px-3 hover:bg-white/15" : "h-10 w-10 justify-center rounded-full bg-transparent px-0 hover:bg-white/10"}`}>
          <div className="flex items-center justify-center shrink-0">
            <MessageSquarePlus size={19} className={!isOpen ? "text-[#dfe7df]" : ""} />
          </div>
          <div className={`flex items-center justify-between overflow-hidden transition-all duration-300 ${isOpen ? "flex-1 opacity-100 ml-2" : "flex-none opacity-0 invisible w-0 m-0"}`}>
            <span>Nuevo chat</span>
            <div className="flex items-center gap-1 text-[11px] text-[#c5cec6]/60">
              <span className="rounded border border-white/20 px-1">Alt</span>
              <span className="rounded border border-white/20 px-1">N</span>
            </div>
          </div>
        </button>
      </div>

      {/* Main Navigation */}
      <div className="flex flex-col gap-1.5 px-1 py-2">
        {navItems.map(({ href, label, icon: Icon, active }) => (
          <button
            key={href}
            onClick={() => router.push(href)}
            title={label}
            aria-label={label}
            className={`flex h-10 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f7f7f2]/70 focus-visible:ring-offset-2 focus-visible:ring-offset-black ${isOpen ? "gap-3 px-3 text-left" : "justify-center px-0"} ${
              active ? "bg-white/10 text-[#f7f7f2]" : "text-[#d8ded7] hover:bg-white/10 hover:text-[#f7f7f2]"
            }`}
          >
            <Icon size={18} className="shrink-0 opacity-80" />
            {isOpen && <span>{label}</span>}
          </button>
        ))}
      </div>

      {/* Utilities */}
      <div className="mt-auto flex flex-col gap-1.5 px-1 pt-6">
        <button
          title="Docs"
          aria-label="Docs"
          className={`flex h-10 items-center rounded-full text-[#d8ded7] transition-colors hover:bg-white/10 hover:text-[#f7f7f2] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f7f7f2]/70 focus-visible:ring-offset-2 focus-visible:ring-offset-black ${isOpen ? "gap-3 px-3 text-left" : "justify-center px-0"}`}
        >
          <HelpCircle size={18} className="shrink-0 opacity-80" />
          {isOpen && <span>Docs</span>}
        </button>
        <button
          onClick={() => router.push("/settings")}
          title="Ajustes"
          aria-label="Ajustes"
          className={`flex h-10 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f7f7f2]/70 focus-visible:ring-offset-2 focus-visible:ring-offset-black ${isOpen ? "gap-3 px-3 text-left" : "justify-center px-0"} ${
            pathname?.startsWith("/settings")
              ? "bg-white/10 text-[#f7f7f2]"
              : "text-[#d8ded7] hover:bg-white/10 hover:text-[#f7f7f2]"
          }`}
        >
          <Settings size={18} className="shrink-0 opacity-80" />
          {isOpen && <span>Ajustes</span>}
        </button>
      </div>

      {/* Profile */}
      <div className={`relative whitespace-nowrap pt-3 transition-all duration-300 ${isOpen ? "px-1" : "px-0"}`}>
        {isProfileOpen && (
          <div className={`absolute bottom-full z-50 mb-2 overflow-hidden rounded-2xl border border-white/10 bg-[#111111] py-1 shadow-2xl shadow-black/40 ${isOpen ? "left-1 right-1" : "left-0 w-52"}`}>
            <div className="mb-1 truncate border-b border-white/10 px-3 py-2 text-xs text-[#aeb9b0]">
              {userEmail}
            </div>
            <button
              onClick={handleLogout}
              className="w-full px-3 py-2 text-left text-sm font-medium text-red-300 transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-300/70"
            >
              Sign out
            </button>
          </div>
        )}
        <button
          onClick={() => setIsProfileOpen(!isProfileOpen)}
          aria-label="Abrir menu de perfil"
          aria-expanded={isProfileOpen}
          className={`mx-auto flex items-center overflow-hidden text-[#d8ded7] transition-all duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f7f7f2]/70 focus-visible:ring-offset-2 focus-visible:ring-offset-black ${isOpen ? "h-12 w-full rounded-full bg-white/[0.07] px-2 hover:bg-white/10" : "h-12 w-12 justify-center rounded-full bg-transparent px-0 hover:bg-white/10"}`}
        >
          <div className="flex items-center justify-center shrink-0">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#15b8c5] text-white">
                <span className="font-semibold text-xs">{userInitial}</span>
            </div>
          </div>
          <div className={`flex items-center justify-between overflow-hidden transition-all duration-300 ${isOpen ? "flex-1 opacity-100 ml-3" : "flex-none opacity-0 invisible w-0 m-0"}`}>
            <span className="text-sm font-medium truncate">{userEmail}</span>
            <ChevronDown size={16} className={`shrink-0 text-[#aeb9b0] transition-transform ${isProfileOpen ? "rotate-180" : ""}`} />
          </div>
        </button>
      </div>
    </aside>

    <nav className="fixed inset-x-3 bottom-3 z-[90] rounded-2xl border border-white/10 bg-black/90 px-2 py-2 shadow-2xl shadow-black/50 backdrop-blur-xl supports-[padding:max(0px)]:bottom-[max(0.75rem,env(safe-area-inset-bottom))] md:hidden">
      <div className="grid grid-cols-5 gap-1">
        {navItems.map(({ href, label, icon: Icon, active }) => (
          <button
            key={href}
            onClick={() => router.push(href)}
            aria-label={label}
            className={`flex min-w-0 flex-col items-center justify-center gap-1 rounded-xl px-1 py-2 text-[10px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f7f7f2]/70 ${
              active
                ? "bg-white/15 text-[#f7f7f2]"
                : "text-[#aeb9b0] hover:bg-white/10 hover:text-[#f7f7f2]"
            }`}
          >
            <Icon size={17} strokeWidth={active ? 2.4 : 2} />
            <span className="w-full truncate text-center">{label}</span>
          </button>
        ))}
      </div>
    </nav>
    </>
  );
}
