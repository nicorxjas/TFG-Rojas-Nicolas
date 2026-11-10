import { Search } from 'lucide-react';
import { AgentAvatarGroup } from '@/components/agentes/AgentAvatarGroup';
import { cn } from '@/lib/utils';
import { Report, ReportAgent } from '@/types/informes';

interface InformesFeedProps {
  reports: Report[];
  selectedId: string;
  onSelect: (id: string) => void;
  className?: string;
}

export default function InformesFeed({ reports, selectedId, onSelect, className }: InformesFeedProps) {
  
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'FAILED': return 'bg-red-400';
      case 'PENDING': 
      case 'GENERATING': return 'bg-yellow-400';
      case 'SUCCESS': return 'bg-emerald-400';
      default: return 'bg-zinc-500';
    }
  };

  return (
    <section className={cn("w-full md:w-[30%] md:min-w-[320px] md:max-w-[380px] bg-zinc-950/60 md:border-r border-zinc-900 flex flex-col font-sans", className)}>
      {/* Search Header */}
      <div className="h-16 md:h-20 px-4 md:px-6 flex items-center border-b border-zinc-900/50 shrink-0 relative">
        <Search size={14} className="text-zinc-500 absolute left-4 md:left-6" />
        <input 
          type="text" 
          placeholder="Search..." 
          className="w-full bg-transparent border-none outline-none text-sm text-zinc-200 pl-8 placeholder:text-zinc-600 font-medium"
        />
      </div>

      <div className="flex-1 overflow-y-auto w-full">
        {reports.length === 0 && (
           <div className="px-6 py-10 text-center text-sm text-zinc-600">
             No hay informes generados. Crea uno nuevo.
           </div>
        )}

        {reports.map((report) => {
          const isActive = report.id === selectedId;
          const dateObj = new Date(report.created_at);
          const dayNum = dateObj.getDate().toString().padStart(2, '0');
          const dayName = dateObj.toLocaleDateString('es', { weekday: 'short' }).replace('.', '');
          const monthName = dateObj.toLocaleDateString('es', { month: 'short' }).replace('.', '');

          const title = report.name || "Informe Sin Título";
          
          // Get participating agents
          const agents = (report.report_agents || [])
            .map((ra) => ra.agents)
            .filter((agent): agent is ReportAgent => Boolean(agent));

          return (
            <button
              key={report.id}
              onClick={() => onSelect(report.id)}
              className={`w-full text-left py-5 md:py-6 px-4 md:px-6 relative transition-colors border-b border-zinc-900/30 flex gap-4 md:gap-5 ${
                isActive ? 'bg-black/[0.035] dark:bg-white/[0.045]' : 'hover:bg-black/[0.025] dark:hover:bg-white/[0.035]'
              }`}
            >
              {/* Date Column */}
              <div className="flex flex-col items-center justify-center shrink-0 w-12 opacity-80 text-center">
                <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-wider mb-1">
                  {monthName}
                </span>
                <span className={`text-2xl font-light tracking-tighter leading-none ${isActive ? 'text-zinc-200' : 'text-zinc-400'}`}>
                  {dayNum}
                </span>
                <span className="text-[10px] font-medium text-zinc-600 mt-1 uppercase tracking-wider">
                  {dayName}
                </span>
              </div>
              
              {/* Content Column */}
              <div className="flex-1 pr-2">
                <div className="flex justify-between items-start relative">
                  {/* Status Indicator Dot */}
                  <div className={`absolute -right-1 top-1.5 w-1.5 h-1.5 rounded-full ${getStatusColor(report.status)} opacity-80`} />
                  
                  <h3 className={`text-[15px] font-medium pr-4 leading-snug ${isActive ? 'text-zinc-100' : 'text-zinc-300'}`}>
                    {title}
                  </h3>
                </div>
                

                {/* Agents Avatar Group */}
                {agents.length > 0 && (
                  <div className="mt-3">
                    <AgentAvatarGroup agents={agents} />
                  </div>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
