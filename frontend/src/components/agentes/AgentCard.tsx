"use client";

import { MoreHorizontal, Trash2, Bot, TrendingDown, DollarSign, TrendingUp, AlertTriangle, Star, Package, Settings, ShoppingCart, Users } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { Agent } from "@/app/agentes/types";
import { AgentVisualIcon } from "./agent-icon";

interface AgentCardProps {
  agent: Agent;
  onClick: () => void;
  onDelete: (id: string) => void;
}

const CATEGORY_CONFIG: Record<
  string,
  {
    icon: React.ReactNode;
    label: string;
    gradient: string;
    iconColor: string;
    bgGlow: string;
  }
> = {
  stock: {
    icon: <Package size={18} strokeWidth={2} />,
    label: "Stock",
    gradient: "from-orange-600/90 to-amber-500/90 shadow-[0_0_10px_rgba(249,115,22,0.2)]",
    iconColor: "text-white",
    bgGlow: "bg-orange-500/5",
  },
  operaciones: {
    icon: <Settings size={18} strokeWidth={2} />,
    label: "Operaciones",
    gradient: "from-teal-600/90 to-emerald-500/90 shadow-[0_0_10px_rgba(20,184,166,0.2)]",
    iconColor: "text-white",
    bgGlow: "bg-teal-500/5",
  },
  ventas: {
    icon: <ShoppingCart size={18} strokeWidth={2} />,
    label: "Ventas",
    gradient: "from-fuchsia-600/90 to-pink-500/90 shadow-[0_0_10px_rgba(217,70,239,0.2)]",
    iconColor: "text-white",
    bgGlow: "bg-fuchsia-500/5",
  },
  clientes: {
    icon: <Users size={18} strokeWidth={2} />,
    label: "Clientes",
    gradient: "from-indigo-600/90 to-purple-500/90 shadow-[0_0_10px_rgba(99,102,241,0.2)]",
    iconColor: "text-white",
    bgGlow: "bg-indigo-500/5",
  },
  finanzas: {
    icon: <DollarSign size={18} strokeWidth={2} />,
    label: "Finanzas",
    gradient: "from-emerald-600/90 to-teal-500/90 shadow-[0_0_10px_rgba(16,185,129,0.2)]",
    iconColor: "text-white",
    bgGlow: "bg-emerald-500/5",
  },
  churn: {
    icon: <TrendingDown size={18} strokeWidth={2} />,
    label: "Churn",
    gradient: "from-rose-600/90 to-orange-500/90 shadow-[0_0_10px_rgba(244,63,94,0.2)]",
    iconColor: "text-white",
    bgGlow: "bg-rose-500/5",
  },
  oportunidad: {
    icon: <TrendingUp size={18} strokeWidth={2} />,
    label: "Oportunidad",
    gradient: "from-sky-600/90 to-blue-500/90 shadow-[0_0_10px_rgba(14,165,233,0.2)]",
    iconColor: "text-white",
    bgGlow: "bg-sky-500/5",
  },
  riesgos: {
    icon: <AlertTriangle size={18} strokeWidth={2} />,
    label: "Riesgos",
    gradient: "from-amber-600/90 to-yellow-500/90 shadow-[0_0_10px_rgba(245,158,11,0.2)]",
    iconColor: "text-white",
    bgGlow: "bg-amber-500/5",
  },
  default: {
    icon: <Bot size={18} strokeWidth={2} />,
    label: "General",
    gradient: "from-violet-600/90 to-fuchsia-500/90 shadow-[0_0_10px_rgba(139,92,246,0.2)]",
    iconColor: "text-white",
    bgGlow: "bg-violet-500/5",
  },
};

function getCategoryConfig(category?: string) {
  const key = category?.toLowerCase() ?? "";
  return CATEGORY_CONFIG[key] ?? CATEGORY_CONFIG.default;
}

export function AgentCard({ agent, onClick, onDelete }: AgentCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [isStarred, setIsStarred] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const confirmRef = useRef(false);

  const { label, gradient, bgGlow } = getCategoryConfig(agent.category);

  // Close menu when clicking outside
  useEffect(() => {
    if (!menuOpen) return;
    const handleOutsideClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
        setConfirmDelete(false);
        confirmRef.current = false;
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [menuOpen]);

  const handleMenuToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    setMenuOpen((v) => !v);
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirmRef.current) {
      onDelete(agent.id);
      setMenuOpen(false);
      setConfirmDelete(false);
      confirmRef.current = false;
    } else {
      confirmRef.current = true;
      setConfirmDelete(true);
      setTimeout(() => {
        confirmRef.current = false;
        setConfirmDelete(false);
      }, 3000);
    }
  };

  const handleStarToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsStarred((v) => !v);
  };

  return (
    <div
      onClick={onClick}
      className="group relative bg-[#0f0f11] border border-zinc-800/80 rounded-xl p-3 flex flex-col items-center justify-between
                 aspect-[3.2/4] min-h-[135px] transition-all duration-300 select-none cursor-pointer
                 hover:border-zinc-700/80 hover:shadow-[0_8px_20px_rgba(0,0,0,0.5)] hover:-translate-y-0.5"
    >
      {/* Background glow matching category */}
      <div className={`absolute inset-0 rounded-xl transition-opacity duration-300 opacity-0 group-hover:opacity-100 ${bgGlow}`} />

      {/* ── Top Bar: Star & Menu ── */}
      <div className="w-full flex items-center justify-between relative z-50 shrink-0">
        <div className="flex items-center">
          {/* Star Rating Button */}
          <button
            onClick={handleStarToggle}
            className={`transition-colors duration-200 p-0.5 rounded-md hover:bg-zinc-800/60
              ${isStarred 
                ? "text-yellow-500" 
                : "text-zinc-600 hover:text-zinc-400"
              }`}
          >
            <Star size={12} fill={isStarred ? "currentColor" : "none"} />
          </button>
        </div>

        {/* Kebab Action Menu */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={handleMenuToggle}
            className="w-5 h-5 flex items-center justify-center text-zinc-500 hover:text-zinc-300 rounded-md hover:bg-zinc-800/60 transition-colors"
          >
            <MoreHorizontal size={12} />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-6 z-30 w-36 bg-zinc-900 border border-zinc-800 rounded-lg shadow-xl overflow-hidden animate-in fade-in slide-in-from-top-1 duration-100">
              <button
                onClick={handleDelete}
                className={[
                  "w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors text-left",
                  confirmDelete
                    ? "text-red-400 bg-red-500/10"
                    : "text-zinc-400 hover:text-red-400 hover:bg-zinc-800",
                ].join(" ")}
              >
                <Trash2 size={12} />
                {confirmDelete ? "¿Confirmar?" : "Eliminar"}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── Center & Bottom Content: only this area opens the modal ── */}
      <div
        className="flex-1 flex flex-col items-center justify-center w-full py-1"
      >
        <div
          className={`w-9 h-9 rounded-lg bg-gradient-to-br ${gradient} flex items-center justify-center
                     transition-transform duration-300 group-hover:scale-105 mb-2 shrink-0`}
        >
          <AgentVisualIcon agent={agent} size={18} className="text-white" />
        </div>
        <div className="w-full text-center shrink-0">
          <h3 
            className="text-xs font-semibold text-zinc-100 leading-snug truncate max-w-full px-1"
            title={agent.name}
          >
            {agent.name}
          </h3>
          <p className="text-[9px] font-semibold text-zinc-500 mt-0.5 uppercase tracking-wider">
            {label}
          </p>
        </div>
      </div>
    </div>
  );
}
