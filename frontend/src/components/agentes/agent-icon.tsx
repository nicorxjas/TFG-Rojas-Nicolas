"use client";

import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  Boxes,
  BrainCircuit,
  BriefcaseBusiness,
  Building2,
  Calculator,
  ChartNoAxesCombined,
  ClipboardList,
  Cpu,
  Database,
  DollarSign,
  Eye,
  FileText,
  Globe2,
  Handshake,
  HeartPulse,
  Lightbulb,
  LineChart,
  Megaphone,
  MessageCircle,
  Network,
  Package,
  PieChart,
  Rocket,
  Search,
  Settings,
  Shield,
  ShoppingCart,
  Sparkles,
  Star,
  Tags,
  Target,
  TrendingDown,
  TrendingUp,
  Truck,
  Users,
  WandSparkles,
  Wrench,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { Agent } from "@/app/agentes/types";

export const AGENT_ICON_COLORS = [
  "#d4d4d8",
  "#94a3b8",
  "#6366f1",
  "#22b8cf",
  "#4ade80",
  "#facc15",
  "#fb923c",
  "#fecaca",
  "#f87171",
];

export const AGENT_ICON_OPTIONS: { name: string; label: string; icon: LucideIcon; keywords: string[] }[] = [
  { name: "bot", label: "Bot", icon: Bot, keywords: ["ai", "agent", "general"] },
  { name: "brain-circuit", label: "Brain", icon: BrainCircuit, keywords: ["ai", "intelligence", "model"] },
  { name: "sparkles", label: "Sparkles", icon: Sparkles, keywords: ["magic", "enhance", "ai"] },
  { name: "wand-sparkles", label: "Wand", icon: WandSparkles, keywords: ["improve", "magic"] },
  { name: "cpu", label: "CPU", icon: Cpu, keywords: ["system", "compute"] },
  { name: "message-circle", label: "Chat", icon: MessageCircle, keywords: ["chat", "conversation"] },
  { name: "database", label: "Database", icon: Database, keywords: ["data", "warehouse"] },
  { name: "search", label: "Search", icon: Search, keywords: ["research", "find"] },
  { name: "chart-no-axes-combined", label: "Chart", icon: ChartNoAxesCombined, keywords: ["analytics", "bi"] },
  { name: "bar-chart-3", label: "Bars", icon: BarChart3, keywords: ["metrics", "analytics"] },
  { name: "line-chart", label: "Line", icon: LineChart, keywords: ["trend", "growth"] },
  { name: "pie-chart", label: "Pie", icon: PieChart, keywords: ["share", "segments"] },
  { name: "dollar-sign", label: "Finance", icon: DollarSign, keywords: ["finance", "money"] },
  { name: "trending-down", label: "Churn", icon: TrendingDown, keywords: ["churn", "risk"] },
  { name: "trending-up", label: "Growth", icon: TrendingUp, keywords: ["growth", "opportunity"] },
  { name: "alert-triangle", label: "Risk", icon: AlertTriangle, keywords: ["risk", "alert"] },
  { name: "package", label: "Stock", icon: Package, keywords: ["inventory", "stock"] },
  { name: "boxes", label: "Boxes", icon: Boxes, keywords: ["inventory", "warehouse"] },
  { name: "truck", label: "Logistics", icon: Truck, keywords: ["shipping", "operations"] },
  { name: "shopping-cart", label: "Sales", icon: ShoppingCart, keywords: ["sales", "commerce"] },
  { name: "users", label: "Customers", icon: Users, keywords: ["clients", "people"] },
  { name: "handshake", label: "Deals", icon: Handshake, keywords: ["sales", "agreement"] },
  { name: "target", label: "Target", icon: Target, keywords: ["goal", "focus"] },
  { name: "lightbulb", label: "Ideas", icon: Lightbulb, keywords: ["insight", "ideas"] },
  { name: "shield", label: "Security", icon: Shield, keywords: ["security", "guard"] },
  { name: "heart-pulse", label: "Health", icon: HeartPulse, keywords: ["health", "status"] },
  { name: "activity", label: "Activity", icon: Activity, keywords: ["signals", "monitor"] },
  { name: "eye", label: "Observe", icon: Eye, keywords: ["watch", "inspect"] },
  { name: "star", label: "Star", icon: Star, keywords: ["favorite", "quality"] },
  { name: "rocket", label: "Launch", icon: Rocket, keywords: ["launch", "speed"] },
  { name: "zap", label: "Zap", icon: Zap, keywords: ["fast", "energy"] },
  { name: "briefcase-business", label: "Business", icon: BriefcaseBusiness, keywords: ["business", "work"] },
  { name: "building-2", label: "Company", icon: Building2, keywords: ["company", "org"] },
  { name: "globe-2", label: "Market", icon: Globe2, keywords: ["global", "market"] },
  { name: "network", label: "Network", icon: Network, keywords: ["model", "semantic"] },
  { name: "clipboard-list", label: "Tasks", icon: ClipboardList, keywords: ["tasks", "list"] },
  { name: "file-text", label: "Report", icon: FileText, keywords: ["report", "document"] },
  { name: "calculator", label: "Calc", icon: Calculator, keywords: ["math", "finance"] },
  { name: "megaphone", label: "Campaign", icon: Megaphone, keywords: ["marketing", "announce"] },
  { name: "tags", label: "Tags", icon: Tags, keywords: ["labels", "taxonomy"] },
  { name: "settings", label: "Ops", icon: Settings, keywords: ["operations", "settings"] },
  { name: "wrench", label: "Tools", icon: Wrench, keywords: ["tools", "fix"] },
];

export function getAgentIconOption(name?: string) {
  return AGENT_ICON_OPTIONS.find((option) => option.name === name) ?? AGENT_ICON_OPTIONS[0];
}

export function getDefaultAgentIconName(category?: string) {
  const key = category?.toLowerCase();
  const defaults: Record<string, string> = {
    stock: "package",
    operaciones: "settings",
    ventas: "shopping-cart",
    clientes: "users",
    finanzas: "dollar-sign",
    churn: "trending-down",
    oportunidad: "trending-up",
    riesgos: "alert-triangle",
    general: "bot",
  };

  return defaults[key ?? ""] ?? "bot";
}

export function AgentVisualIcon({
  agent,
  size = 18,
  className,
}: {
  agent: Pick<Agent, "category" | "iconType" | "iconName" | "iconColor" | "iconEmoji">;
  size?: number;
  className?: string;
}) {
  if (agent.iconType === "emoji" && agent.iconEmoji) {
    return (
      <span className={className} style={{ fontSize: size, lineHeight: 1 }}>
        {agent.iconEmoji}
      </span>
    );
  }

  const Icon = getAgentIconOption(agent.iconName ?? getDefaultAgentIconName(agent.category)).icon;
  return (
    <Icon
      size={size}
      strokeWidth={2}
      className={className}
      style={{ color: agent.iconColor ?? AGENT_ICON_COLORS[0] }}
    />
  );
}
