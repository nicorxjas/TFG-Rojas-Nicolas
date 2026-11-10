"use client";

import { AgentVisualIcon } from "@/components/agentes/agent-icon";

type AgentAvatar = {
  id: string;
  name: string;
  category?: string | null;
  iconType?: "icon" | "emoji";
  iconName?: string;
  iconColor?: string;
  iconEmoji?: string;
  icon_type?: "icon" | "emoji" | null;
  icon_name?: string | null;
  icon_color?: string | null;
  icon_emoji?: string | null;
};

function getVisualAgent(agent: AgentAvatar) {
  return {
    category: agent.category ?? undefined,
    iconType: agent.iconType ?? agent.icon_type ?? undefined,
    iconName: agent.iconName ?? agent.icon_name ?? undefined,
    iconColor: agent.iconColor ?? agent.icon_color ?? undefined,
    iconEmoji: agent.iconEmoji ?? agent.icon_emoji ?? undefined,
  };
}

export function AgentAvatarGroup({
  agents,
  maxVisible = 6,
  sizeClassName = "h-7 w-7",
  iconSize = 12,
}: {
  agents: AgentAvatar[];
  maxVisible?: number;
  sizeClassName?: string;
  iconSize?: number;
}) {
  const visibleAgents = agents.slice(0, maxVisible);
  const hasMore = agents.length > maxVisible;

  return (
    <div className="flex items-center pl-2">
      {visibleAgents.map((agent) => (
        <div key={agent.id} className="group relative z-0 -ml-2 first:ml-0 hover:z-20">
          <div
            className={`${sizeClassName} flex shrink-0 cursor-pointer items-center justify-center rounded-full border-2 border-zinc-950 bg-zinc-900 text-zinc-200 shadow-md transition-all duration-300 ease-in-out group-hover:-translate-y-1 group-hover:bg-zinc-800 group-hover:shadow-lg`}
          >
            <AgentVisualIcon agent={getVisualAgent(agent)} size={iconSize} />
          </div>

          <div className="pointer-events-none absolute bottom-[calc(100%+8px)] left-1/2 z-[70] -translate-x-1/2 scale-95 whitespace-nowrap rounded-[5px] border border-zinc-800/80 bg-[#09090b] px-2.5 py-1 font-sans text-[10px] text-zinc-300 opacity-0 shadow-2xl transition-all duration-300 group-hover:scale-100 group-hover:opacity-100">
            <div className="text-left font-medium text-zinc-100">{agent.name}</div>
          </div>
        </div>
      ))}

      {hasMore && (
        <div
          className={`${sizeClassName} -ml-2 flex shrink-0 select-none items-center justify-center rounded-full border-2 border-zinc-950 bg-zinc-900 text-[11px] font-semibold text-zinc-300 shadow-md transition-all hover:z-10 hover:-translate-y-1 hover:bg-zinc-800 hover:text-zinc-100`}
          title={`${agents.length - maxVisible} agentes mas`}
        >
          +{agents.length - maxVisible}
        </div>
      )}
    </div>
  );
}
