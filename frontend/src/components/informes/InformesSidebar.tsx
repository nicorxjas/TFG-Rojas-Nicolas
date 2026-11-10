import { Inbox, AlertCircle, Star, FilePlus2 } from 'lucide-react';
import { useInformesSidebarStore } from '@/lib/store';

interface InformesSidebarProps {
  onNewReport?: () => void;
}

export default function InformesSidebar({ onNewReport }: InformesSidebarProps) {
  const { isOpen, toggleSidebar } = useInformesSidebarStore();

  const departments = [
    { name: 'Ventas', color: 'bg-blue-400' },
    { name: 'RRHH', color: 'bg-emerald-400' },
    { name: 'Operaciones', color: 'bg-amber-400' },
    { name: 'IT', color: 'bg-violet-400' },
    { name: 'Finanzas', color: 'bg-pink-400' }
  ];

  return (
    <aside className={`${
      isOpen 
        ? "w-[20%] min-w-[220px] max-w-[280px]" 
        : "w-[68px] min-w-[68px] max-w-[68px]"
    } h-full hidden md:flex flex-col font-sans border-r border-zinc-900/50 bg-zinc-950/40 shrink-0 transition-all duration-300 ease-in-out`}>
      {/* Top spacing / Header */}
      <div className={`h-20 flex items-center shrink-0 transition-all duration-300 ${isOpen ? "px-6" : "justify-center px-0"}`}>
        <button 
          onClick={toggleSidebar}
          title={isOpen ? "Colapsar menú" : "Expandir menú"}
          className="flex items-center justify-center w-8 h-8 rounded-md bg-transparent hover:bg-zinc-900 text-zinc-400 hover:text-zinc-100 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6h16M4 12h16M4 18h7" />
          </svg>
        </button>
      </div>

      <div className={`flex-1 overflow-y-auto space-y-10 pt-4 transition-all duration-300 ${isOpen ? "px-6" : "px-3 flex flex-col items-center"}`}>
        {/* Create Button */}
        <div className="w-full flex justify-center">
          <button
            onClick={onNewReport}
            title="Crear Informe"
            className={`flex items-center justify-center transition-all duration-300 text-zinc-950 bg-zinc-100 hover:bg-white rounded-lg shadow-sm whitespace-nowrap overflow-hidden ${
              isOpen 
                ? "w-full py-2.5 px-4 font-medium text-sm" 
                : "w-10 h-10 px-0"
            }`}
          >
            <FilePlus2 size={isOpen ? 16 : 20} className="shrink-0 transition-all duration-300" />
            <span className={`transition-all duration-300 ease-in-out whitespace-nowrap overflow-hidden ${
              isOpen 
                ? "opacity-100 max-w-[150px] ml-2" 
                : "opacity-0 max-w-0 ml-0 pointer-events-none"
            }`}>
              Crear Informe
            </span>
          </button>
        </div>

        {/* Views */}
        <div className="w-full">
          {isOpen && <h2 className="text-sm font-medium text-zinc-100 mb-4 transition-all duration-300">Views</h2>}
          <nav className={`space-y-1.5 ${!isOpen && "flex flex-col items-center"}`}>
            <button 
              title="Inbox"
              className={`flex items-center transition-all duration-300 group whitespace-nowrap overflow-hidden ${
                isOpen 
                  ? "w-full py-1.5 px-3 text-[13px] text-zinc-400 hover:text-zinc-200 rounded-lg hover:bg-zinc-900/40" 
                  : "w-10 h-10 justify-center rounded-lg hover:bg-zinc-900 text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <Inbox size={isOpen ? 14 : 18} className="text-zinc-500 group-hover:text-zinc-400 shrink-0 transition-all duration-300" />
              <span className={`transition-all duration-300 ease-in-out whitespace-nowrap overflow-hidden ${
                isOpen 
                  ? "opacity-100 max-w-[100px] ml-3" 
                  : "opacity-0 max-w-0 ml-0 pointer-events-none"
              }`}>
                Inbox
              </span>
            </button>
            <button 
              title="High Alerts"
              className={`flex items-center transition-all duration-300 group whitespace-nowrap overflow-hidden ${
                isOpen 
                  ? "w-full py-1.5 px-3 text-[13px] text-zinc-400 hover:text-zinc-200 rounded-lg hover:bg-zinc-900/40" 
                  : "w-10 h-10 justify-center rounded-lg hover:bg-zinc-900 text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <AlertCircle size={isOpen ? 14 : 18} className="text-zinc-500 group-hover:text-red-400 shrink-0 transition-all duration-300" />
              <span className={`transition-all duration-300 ease-in-out whitespace-nowrap overflow-hidden ${
                isOpen 
                  ? "opacity-100 max-w-[100px] ml-3" 
                  : "opacity-0 max-w-0 ml-0 pointer-events-none"
              }`}>
                High Alerts
              </span>
            </button>
            <button 
              title="Favorites"
              className={`flex items-center transition-all duration-300 group whitespace-nowrap overflow-hidden ${
                isOpen 
                  ? "w-full py-1.5 px-3 text-[13px] text-zinc-400 hover:text-zinc-200 rounded-lg hover:bg-zinc-900/40" 
                  : "w-10 h-10 justify-center rounded-lg hover:bg-zinc-900 text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <Star size={isOpen ? 14 : 18} className="text-zinc-500 group-hover:text-yellow-400 shrink-0 transition-all duration-300" />
              <span className={`transition-all duration-300 ease-in-out whitespace-nowrap overflow-hidden ${
                isOpen 
                  ? "opacity-100 max-w-[100px] ml-3" 
                  : "opacity-0 max-w-0 ml-0 pointer-events-none"
              }`}>
                Favorites
              </span>
            </button>
          </nav>
        </div>

        {/* Departments Tags */}
        {isOpen && (
          <div className="w-full">
            <h2 className="text-sm font-medium text-zinc-100 mb-4">Departments</h2>
            <nav className="space-y-2">
              {departments.map((dept) => (
                <button key={dept.name} className="w-full flex items-center space-x-3 py-1 text-[13px] text-zinc-400 hover:text-zinc-200 transition-colors">
                  <span className={`w-1.5 h-1.5 rounded-full ${dept.color}`} />
                  <span>{dept.name}</span>
                </button>
              ))}
            </nav>
          </div>
        )}
      </div>
    </aside>
  );
}
