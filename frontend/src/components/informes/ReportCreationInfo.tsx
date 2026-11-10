import { Agent } from "@/app/agentes/types";
import { AgentVisualIcon } from "@/components/agentes/agent-icon";
import { Report, ReportAgent } from "@/types/informes";

interface ReportCreationInfoProps {
  report: Report;
}

function mapReportAgent(agent: ReportAgent): Agent {
  return {
    id: agent.id,
    name: agent.name,
    description: agent.description ?? "",
    systemPrompt: agent.systemPrompt ?? agent.system_prompt ?? "",
    category: agent.category ?? "general",
    iconType: agent.iconType ?? agent.icon_type ?? "icon",
    iconName: agent.iconName ?? agent.icon_name ?? undefined,
    iconColor: agent.iconColor ?? agent.icon_color ?? undefined,
    iconEmoji: agent.iconEmoji ?? agent.icon_emoji ?? undefined,
    createdAt: agent.createdAt ?? agent.created_at ?? "",
  };
}

export default function ReportCreationInfo({ report }: ReportCreationInfoProps) {
  const prompt = report.prompt ?? "";
  const selectedAgents = (report.report_agents ?? [])
    .map((row) => row.agents)
    .filter((agent): agent is ReportAgent => Boolean(agent))
    .map(mapReportAgent);

  return (
    <div className="flex-1 overflow-y-auto bg-[#0b0b0c]">
      <div className="mx-auto w-full max-w-[760px] px-5 py-8 md:px-0 md:py-14">
        <div className="space-y-8">
          <section className="space-y-2">
            <input
              value={report.name || "Informe de IA"}
              readOnly
              aria-readonly="true"
              tabIndex={-1}
              className="block w-full cursor-default bg-transparent p-0 text-2xl font-semibold leading-tight text-zinc-100 outline-none"
            />
          </section>


          <section className="space-y-3">
            <div>
              <h3 className="text-sm font-semibold text-zinc-100">Agentes</h3>
              <p className="mt-1 text-sm text-zinc-500">Agentes asignados a este informe.</p>
            </div>

            {selectedAgents.length === 0 ? (
              <p className="text-sm text-zinc-600">Sin agentes asignados</p>
            ) : (
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
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="space-y-3">
            <div>
              <h3 className="text-sm font-semibold text-zinc-100">Instrucciones</h3>
            </div>

            <div className="rounded-xl border border-zinc-800 bg-zinc-900/55">
              <textarea
                value={prompt}
                readOnly
                aria-readonly="true"
                placeholder="Sin instrucciones adicionales."
                className="min-h-[220px] w-full cursor-default resize-none bg-transparent px-4 py-4 font-sans text-sm leading-relaxed text-zinc-100 placeholder:text-zinc-600 outline-none"
              />
            </div>

            <div className="flex items-center justify-between gap-3">
              <div className="text-[10px] font-mono text-zinc-600">{prompt.length} chars</div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
