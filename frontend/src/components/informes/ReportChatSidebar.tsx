"use client";

import { ChevronDown, X } from "lucide-react";
import ChatInput from "../chat/ChatInput";
import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Report } from "@/types/informes";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  isLoading?: boolean;
};

interface ReportChatSidebarProps {
  report: Report;
  onClose: () => void;
}

const SUGGESTIONS = [
  {
    title: "Explicar resumen ejecutivo",
    description: "Analizar los insights del resumen del reporte",
    prompt: "Dame un análisis más detallado o una explicación del resumen ejecutivo de este informe.",
  },
  {
    title: "Detallar accionables críticos",
    description: "Prioridades sugeridas para el negocio",
    prompt: "¿Cuáles son los accionables más críticos en este informe y cómo podemos ejecutarlos?",
  },
  {
    title: "Profundizar en el gráfico",
    description: "Extraer insights clave de los datos visualizados",
    prompt: "Analizá en detalle los datos del gráfico de este informe e indicá qué tendencias clave se extraen.",
  },
];

export default function ReportChatSidebar({ report, onClose }: ReportChatSidebarProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Reset messages when report changes
  useEffect(() => {
    setMessages([]);
  }, [report.id]);

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  const handleSendMessage = async (prompt: string) => {
    const userMsgId = Date.now().toString();
    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", content: prompt },
    ]);

    const astMsgId = (Date.now() + 1).toString();
    setMessages((prev) => [
      ...prev,
      { id: astMsgId, role: "assistant", content: "", isLoading: true },
    ]);
    setIsProcessing(true);

    try {
      const historyPayload = messages
        .filter((msg) => !msg.isLoading && !msg.content.startsWith("Error:"))
        .slice(-6)
        .map((msg) => ({ role: msg.role, content: msg.content }));

      const res = await fetch("http://localhost:8000/chat/report", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          prompt,
          report_name: report.name || "Informe de IA",
          report_content: report.content,
          history: historyPayload
        }),
      });

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(`API Error: ${res.status} - ${errorText}`);
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let fullContent = "";
      let buffer = "";

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n\n');
          buffer = lines.pop() || "";

          for (const rawLine of lines) {
            const line = rawLine.trim();
            if (!line.startsWith('data: ')) continue;

            const dataStr = line.substring(6);
            if (!dataStr) continue;

            try {
              const data = JSON.parse(dataStr);
              if (data.type === 'chunk') {
                fullContent += data.content;

                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === astMsgId
                      ? { ...msg, content: fullContent }
                      : msg
                  )
                );
              } else if (data.type === 'error') {
                throw new Error(data.content);
              }
            } catch (e) {
              console.error("Error parsing stream data:", e);
            }
          }
        }
      }

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === astMsgId
            ? { ...msg, isLoading: false }
            : msg
        )
      );

    } catch (error: any) {
      console.error(error);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === astMsgId
            ? { ...msg, content: `Error: ${error.message || "Ocurrió un error al procesar tu pregunta"}`, isLoading: false }
            : msg
        )
      );
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-zinc-950 relative">
      <header className="flex items-center justify-between p-5 pb-16 pt-5 absolute top-0 left-0 right-[8px] z-10 bg-gradient-to-b from-zinc-950 via-zinc-950/95 to-transparent pointer-events-none">
        <div className="flex items-center gap-2 pointer-events-auto">
          <button className="flex items-center gap-2 text-zinc-300 hover:text-white transition-colors">
            <span className="font-semibold text-sm">Nuevo Chat</span>
            <ChevronDown size={14} className="opacity-70 text-zinc-500" />
          </button>
        </div>

        <button
          onClick={onClose}
          className="w-7 h-7 flex items-center justify-center text-zinc-500 hover:text-zinc-200 transition-colors rounded-lg bg-zinc-900/50 border border-zinc-800 hover:bg-zinc-800 pointer-events-auto shadow-sm"
        >
          <X size={14} />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto w-full pt-20 pb-40 flex flex-col">
        {messages.length === 0 && (
          <div className="px-5 py-6">
            <div className="mb-6">
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500 mb-3">Preguntas sugeridas</h4>
              <div className="flex flex-col gap-2.5">
                {SUGGESTIONS.map((sug, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendMessage(sug.prompt)}
                    className="flex flex-col text-left p-4 rounded-xl bg-zinc-900/40 border border-zinc-800/80 hover:border-zinc-700/80 hover:bg-zinc-900/80 hover:-translate-y-0.5 transition-all duration-300 group cursor-pointer shadow-lg hover:shadow-black/40 min-h-[96px] justify-center"
                  >
                    <h4 className="text-sm font-semibold text-zinc-200 group-hover:text-white transition-colors duration-200">
                      {sug.title}
                    </h4>
                    <p className="text-xs text-zinc-500 mt-1 leading-relaxed group-hover:text-zinc-400 transition-colors duration-200">
                      {sug.description}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        <div className="flex flex-col w-full px-5 gap-6 pb-6 mt-4">
          {messages.map((msg) => (
            <div key={msg.id} className={`flex gap-3.5 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`flex flex-col max-w-[85%] ${msg.role === "user" ? "items-end" : "items-start"}`}>
                <div className={
                  msg.role === "user"
                    ? "p-3 px-4 rounded-2xl bg-zinc-800 text-zinc-100 rounded-tr-sm text-[14px] leading-relaxed border border-zinc-700/30"
                    : msg.isLoading && msg.content === ""
                      ? "text-zinc-400 text-[14px] w-full flex items-center gap-2 py-1"
                      : "text-zinc-100 text-[14px] leading-relaxed w-full prose prose-invert prose-sm max-w-none"
                }>
                  {msg.isLoading && msg.content === "" ? (
                    <>
                      <div className="w-3 h-3 border-2 border-zinc-500 border-t-white rounded-full animate-spin shrink-0" />
                      <span>Analizando informe...</span>
                    </>
                  ) : msg.role === "assistant" ? (
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        h1: ({ node, ...props }) => <h1 className="text-base font-semibold text-zinc-100 mt-2 mb-2" {...props} />,
                        h2: ({ node, ...props }) => <h2 className="text-sm font-semibold text-zinc-100 mt-2 mb-1" {...props} />,
                        p: ({ node, ...props }) => <p className="mb-2 last:mb-0 leading-relaxed text-zinc-100" {...props} />,
                        ul: ({ node, ...props }) => <ul className="list-disc pl-4 mb-2 space-y-1 text-zinc-100" {...props} />,
                        ol: ({ node, ...props }) => <ol className="list-decimal pl-4 mb-2 space-y-1 text-zinc-100" {...props} />,
                        li: ({ node, ...props }) => <li className="text-zinc-100" {...props} />,
                        strong: ({ node, ...props }) => <strong className="font-semibold text-zinc-100" {...props} />,
                      }}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  ) : (
                    <span className="whitespace-pre-wrap">{msg.content}</span>
                  )}
                </div>
              </div>

            </div>
          ))}
          <div ref={bottomRef} className="h-4" />
        </div>
      </div>

      <div className="absolute bottom-0 left-0 right-[8px] bg-gradient-to-t from-zinc-950 via-zinc-950 to-transparent pt-10 pb-3 px-4">
        <ChatInput 
          onSend={handleSendMessage} 
          isLoading={isProcessing} 
          placeholder="Pregunta sobre este informe..."
        />
      </div>
    </div>
  );
}
