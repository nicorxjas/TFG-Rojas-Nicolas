import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Download, Star, MessageSquare, Trash, ChevronLeft, ChevronRight, Forward, RefreshCw, Info } from 'lucide-react';
import { Report } from '@/types/informes';
import ReportChatSidebar from './ReportChatSidebar';
import ReportCreationInfo from './ReportCreationInfo';

interface InformesReaderProps {
  report: Report;
  onDelete?: (id: string) => void;
  onBack?: () => void;
  onRegenerate?: (id: string) => void;
}

function withoutMarkdownNode<T extends { node?: unknown }>(props: T) {
  const { node, ...rest } = props;
  void node;
  return rest;
}

export default function InformesReader({ report, onDelete, onBack, onRegenerate }: InformesReaderProps) {
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isFavorite, setIsFavorite] = useState(false);
  const [infoState, setInfoState] = useState({ reportId: report.id, open: false });
  const content = report.content;
  const isInfoOpen = infoState.reportId === report.id ? infoState.open : false;

  return (
    <section className="flex-1 w-full min-w-0 md:min-w-[500px] h-full flex bg-zinc-950/60 font-sans relative overflow-hidden">
      {/* Lado Izquierdo: Lector de Informe */}
      <div className="flex-1 h-full flex flex-col relative border-r border-zinc-900/50 overflow-hidden">
      {/* Header (Top Icons) */}
      <header className="h-16 md:h-20 px-4 md:px-10 border-b border-zinc-900/50 flex items-center justify-between shrink-0">
        <div className="flex items-center space-x-4 text-zinc-500">
          {onBack && (
            <button onClick={onBack} className="md:hidden hover:text-zinc-300 transition-colors">
              <ChevronLeft size={20} />
            </button>
          )}
          <button className="hover:text-zinc-300 transition-colors pointer-events-none opacity-50"><ChevronLeft size={18} /></button>
          <button className="hover:text-zinc-300 transition-colors pointer-events-none opacity-50"><ChevronRight size={18} /></button>
        </div>
        <div className="flex items-center space-x-4 md:space-x-6 text-zinc-500">
          <button
            onClick={() => {
              setInfoState((current) => ({
                reportId: report.id,
                open: current.reportId === report.id ? !current.open : true,
              }));
            }}
            className={`transition-colors duration-200 ${
              isInfoOpen ? 'text-zinc-100 hover:text-zinc-200' : 'hover:text-zinc-300'
            }`}
            title="Informacion de creacion"
            aria-pressed={isInfoOpen}
          >
            <Info size={16} />
          </button>
          <button 
            onClick={() => setIsFavorite(!isFavorite)}
            className={`transition-colors duration-200 ${
              isFavorite ? 'text-yellow-400 hover:text-yellow-300' : 'hover:text-zinc-300'
            }`}
            title="Favorito"
          >
            <Star size={16} className={isFavorite ? "fill-yellow-400" : ""} />
          </button>
          <button className="hover:text-zinc-300 transition-colors" title="Exportar">
            <Download size={16} />
          </button>
          <button className="hover:text-zinc-300 transition-colors" title="Compartir">
            <Forward size={16} />
          </button>
          <button
            className="hover:text-zinc-300 transition-colors"
            onClick={() => onRegenerate?.(report.id)}
            title="Regenerar"
          >
            <RefreshCw size={16} />
          </button>
          <button
            className="hover:text-red-400 transition-colors"
            onClick={() => onDelete?.(report.id)}
            title="Eliminar"
          >
            <Trash size={16} />
          </button>
          <button className="hidden sm:flex items-center justify-center w-8 h-8 rounded bg-[#B7FF1F] hover:bg-white text-black transition-colors ml-4 shadow-sm">
            <span className="text-xl leading-none -mt-0.5 font-medium">+</span>
          </button>
        </div>
      </header>

      {/* Content */}
      {isInfoOpen ? (
        <ReportCreationInfo report={report} />
      ) : (
      <div className="flex-1 overflow-y-auto px-4 md:px-10 pt-8 md:pt-12 pb-32">
        <div className="max-w-3xl mx-auto text-zinc-300">
          <div className="text-zinc-500 mb-6 font-medium text-sm flex items-center">
            <span>{new Date(report.created_at).toLocaleDateString()}</span>
          </div>

          <h1 className="text-3xl md:text-5xl font-normal text-zinc-100 mb-8 md:mb-10 tracking-tight">
            {report.name || "Informe de IA"}
          </h1>

          {report.status === 'PENDING' || report.status === 'GENERATING' ? (
            <div className="flex flex-col items-center justify-center py-20 text-zinc-500 space-y-4">
              <div className="w-8 h-8 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin"></div>
              <p>Procesando insights con IA...</p>
            </div>
          ) : report.status === 'FAILED' ? (
            <div className="p-6 bg-red-950/20 border border-red-900/50 rounded-xl text-red-400">
              <h3 className="font-semibold text-lg mb-2">Error al generar el informe</h3>
              <p className="text-sm font-mono opacity-80">{report.error_log || "Error desconocido"}</p>
            </div>
          ) : content ? (
            <>
              {/* Executive Summary */}
              <div className="prose prose-invert max-w-none">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    img: () => null,
                    h1: (props) => <h1 className="text-3xl font-medium text-zinc-100 mb-8 tracking-tight hidden" {...withoutMarkdownNode(props)} />,
                    h2: (props) => <h2 className="text-xl md:text-2xl font-medium text-zinc-200 mt-10 md:mt-12 mb-5 md:mb-6" {...withoutMarkdownNode(props)} />,
                    h3: (props) => <h3 className="text-lg md:text-xl font-medium text-zinc-200 mt-8 mb-4" {...withoutMarkdownNode(props)} />,
                    p: (props) => <p className="leading-loose mb-6 text-[15px] font-normal text-zinc-400" {...withoutMarkdownNode(props)} />,
                    ul: (props) => <ul className="list-disc pl-5 mb-6 space-y-3" {...withoutMarkdownNode(props)} />,
                    ol: (props) => <ol className="list-decimal pl-5 mb-6 space-y-3" {...withoutMarkdownNode(props)} />,
                    li: (props) => <li className="text-[15px] leading-loose text-zinc-400" {...withoutMarkdownNode(props)} />,
                    strong: (props) => <strong className="font-semibold text-zinc-200" {...withoutMarkdownNode(props)} />,
                  }}
                >
                  {content.executive_summary}
                </ReactMarkdown>
              </div>

              {/* Actionables */}
              {content.actionables && content.actionables.length > 0 && (
                <div className="prose prose-invert max-w-none mt-10 md:mt-12">
                  <h2 className="text-xl md:text-2xl font-medium text-zinc-200 mt-10 md:mt-12 mb-5 md:mb-6">
                    Accionables Sugeridos
                  </h2>
                  <ul className="list-disc pl-5 mb-6 space-y-3">
                    {content.actionables.map((actionable, i) => (
                      <li
                        key={i}
                        className="text-[15px] leading-loose text-zinc-400"
                      >
                        {actionable.text}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

            </>
          ) : (
            <p className="text-zinc-500">El informe no contiene datos o está corrupto.</p>
          )}
        </div>
      </div>
      )}

        {/* Floating Action Button (FAB) for Chat */}
        {!isChatOpen && !isInfoOpen && (
          <button
            onClick={() => setIsChatOpen(true)}
            className="absolute bottom-5 right-5 md:bottom-8 md:right-8 w-14 h-14 rounded-full bg-white hover:bg-zinc-200 text-zinc-950 flex items-center justify-center shadow-2xl hover:scale-105 active:scale-95 transition-all duration-200 z-40 cursor-pointer"
            title="Preguntar a Synthesis sobre este informe"
          >
            <MessageSquare size={22} className="stroke-[2.5]" />
          </button>
        )}
      </div>

      {/* Lado Derecho: Conversational Chat Panel */}
      {isChatOpen && (
        <div className="absolute inset-0 z-50 md:static md:z-auto w-full md:w-[360px] h-full flex-shrink-0 bg-zinc-950 border-l border-zinc-900">
          <ReportChatSidebar report={report} onClose={() => setIsChatOpen(false)} />
        </div>
      )}
    </section>
  );
}
