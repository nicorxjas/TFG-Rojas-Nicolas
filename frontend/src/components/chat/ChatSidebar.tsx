"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  Loader2,
  Pencil,
  Search,
  X,
} from "lucide-react";
import { motion } from "motion/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ChatInput from "./ChatInput";
import { createClient } from "@/lib/supabase/client";
import { getSupabaseAuthHeaders } from "@/lib/supabase/auth";
import { buildChatHistory } from "@/lib/chat-history";
import { NEW_CHAT_EVENT } from "@/lib/chat-events";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  isLoading?: boolean;
  metricSuggestion?: MetricSuggestion;
  semanticContext?: Record<string, unknown>;
};

type MetricSuggestion = {
  draft_id?: string;
  name: string;
  description: string;
  expression: string;
  format?: string;
  connection_id?: string | null;
  proposed_calculation: string;
  requires_definition?: boolean;
  status?: "pending" | "saving" | "approved" | "rejected" | "error";
  statusMessage?: string;
  alternativeExpression?: string;
  selectedOption?: "approve" | "reject" | "custom";
  sourcePrompt?: string;
};

type ProfileRow = {
  full_name: string | null;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const CHAT_BACKGROUND_STYLE: React.CSSProperties = {
  backgroundColor: "#A6B5A8",
  backgroundImage:
    "linear-gradient(180deg, rgba(166,181,168,0.96) 0%, rgba(143,169,164,0.78) 42%, rgba(59,80,76,0.48) 100%), url('/media/nyro-chat-clouds-4k.jpg')",
  backgroundPosition: "center bottom",
  backgroundRepeat: "no-repeat",
  backgroundSize: "cover",
};

const DITHER_STYLE: React.CSSProperties = {
  backgroundImage: "radial-gradient(rgba(26, 53, 56, 0.42) 0.9px, transparent 0.9px)",
  backgroundSize: "5px 5px",
  maskImage: "linear-gradient(to top, rgba(0,0,0,1), rgba(0,0,0,0.82) 52%, rgba(0,0,0,0))",
  WebkitMaskImage: "linear-gradient(to top, rgba(0,0,0,1), rgba(0,0,0,0.82) 52%, rgba(0,0,0,0))",
};

const TOP_FADE_STYLE: React.CSSProperties = {
  background: "linear-gradient(180deg, rgba(166,181,168,0.92), rgba(166,181,168,0.54) 58%, rgba(166,181,168,0))",
};

const BOTTOM_FADE_STYLE: React.CSSProperties = {
  background: "linear-gradient(0deg, rgba(24,32,31,0.78), rgba(24,32,31,0.38) 52%, rgba(24,32,31,0))",
};

const SUGGESTIONS = [
  {
    starter: "weekly_sales" as const,
    title: "Analizar ventas de la semana",
    description: "Tendencia, ticket promedio y volumen",
    prompt: "Analiza la tendencia del ticket promedio y el volumen de transacciones de la última semana.",
  },
  {
    starter: "churn" as const,
    title: "Detectar riesgo de abandono",
    description: "Patrones de churn y clientes en riesgo",
    prompt: "Analiza los patrones de comportamiento de los clientes e identifica cuáles tienen mayor riesgo de abandono (churn) y por qué.",
  },
  {
    starter: undefined,
    title: "Oportunidades de up-sell",
    description: "Desempeño por rubro de producto",
    prompt: "Compara el desempeño de ventas por rubro de producto para encontrar oportunidades de up-sell y crecimiento.",
  },
];

function getErrorMessage(error: unknown, fallback = "An error occurred") {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return fallback;
}

function getFirstName(fullName?: string | null) {
  return fullName?.trim().split(/\s+/)[0] ?? "";
}

const MagneticDots = () => (
  <div className="relative flex space-x-1.5" style={{ filter: "url(#nyro-goo)" }}>
    <svg width="0" height="0" className="absolute hidden" aria-hidden>
      <defs>
        <filter id="nyro-goo">
          <feGaussianBlur in="SourceGraphic" stdDeviation="2" result="blur" />
          <feColorMatrix
            in="blur"
            mode="matrix"
            values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 15 -7"
            result="goo"
          />
          <feComposite in="SourceGraphic" in2="goo" operator="atop" />
        </filter>
      </defs>
    </svg>
    <motion.div
      className="h-4 w-4 rounded-full bg-[#f7f7f2]"
      animate={{ x: [0, 8, 0] }}
      transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
    />
    <motion.div
      className="h-4 w-4 rounded-full bg-[#f7f7f2]"
      animate={{ x: [0, -8, 0] }}
      transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
    />
  </div>
);

export const ChatSidebar = () => {
  const isSidebarMode = false;
  const supabase = useMemo(() => createClient(), []);
  const [messages, setMessages] = useState<Message[]>([]);
  const [userName, setUserName] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const streamingScrollTimerRef = useRef<number | null>(null);
  const sessionAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const fetchUserName = async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return;

      const metadata = user.user_metadata as Record<string, string | undefined>;
      const { data: profile } = await supabase
        .from("profiles")
        .select("full_name")
        .eq("id", user.id)
        .maybeSingle<ProfileRow>();

      setUserName(getFirstName(profile?.full_name) || getFirstName(metadata.full_name) || getFirstName(metadata.name));
    };

    fetchUserName();
  }, [supabase]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior });
    }
  }, []);

  const scheduleStreamingScroll = useCallback(() => {
    if (streamingScrollTimerRef.current) return;
    streamingScrollTimerRef.current = window.setTimeout(() => {
      streamingScrollTimerRef.current = null;
      scrollToBottom("auto");
    }, 120);
  }, [scrollToBottom]);

  useEffect(() => {
    const controller = new AbortController();
    sessionAbortRef.current = controller;
    const cancelChat = () => controller.abort();
    window.addEventListener(NEW_CHAT_EVENT, cancelChat);
    return () => {
      window.removeEventListener(NEW_CHAT_EVENT, cancelChat);
      controller.abort();
      if (streamingScrollTimerRef.current) window.clearTimeout(streamingScrollTimerRef.current);
    };
  }, []);

  useEffect(() => {
    scrollToBottom("smooth");
  }, [messages.length, scrollToBottom]);

  const updateMetricSuggestion = useCallback((messageId: string, patch: Partial<MetricSuggestion>) => {
    setMessages((previous) =>
      previous.map((message) =>
        message.id === messageId && message.metricSuggestion
          ? { ...message, metricSuggestion: { ...message.metricSuggestion, ...patch } }
          : message
      )
    );
  }, []);

  const readApiMessage = async (response: Response, fallback: string) => {
    try {
      const payload = await response.json();
      return typeof payload.detail === "string" ? payload.detail : fallback;
    } catch {
      return fallback;
    }
  };

  const answerOriginalQuestion = async (
    messageId: string,
    suggestion: MetricSuggestion,
    metricName: string
  ) => {
    if (sessionAbortRef.current?.signal.aborted) return;
    const controller = sessionAbortRef.current ?? new AbortController();
    sessionAbortRef.current = controller;
    const signal = controller.signal;
    const confirmation = `¡Listo! Creé la métrica **${metricName}**.`;
    const originalPrompt = (suggestion.sourcePrompt || "").trim();
    if (!originalPrompt) {
      setMessages((previous) =>
        previous.map((message) =>
          message.id === messageId && message.metricSuggestion
            ? {
                ...message,
                content: confirmation,
                metricSuggestion: { ...message.metricSuggestion, status: "approved", statusMessage: "" },
              }
            : message
        )
      );
      return;
    }

    updateMetricSuggestion(messageId, {
      status: "saving",
      statusMessage: "Métrica creada. Calculando la respuesta...",
    });
    setIsProcessing(true);

    try {
      const auth = await getSupabaseAuthHeaders();
      if (!auth.headers.Authorization) {
        throw new Error("No pude validar la sesión para calcular el resultado.");
      }

      const suggestionIndex = messages.findIndex((message) => message.id === messageId);
      const contextualMessages = suggestionIndex > 1 ? messages.slice(0, suggestionIndex - 1) : [];
      const historyPayload = buildChatHistory(contextualMessages);

      const response = await fetch(`${apiBaseUrl}/chat/`, {
        signal,
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth.headers },
        body: JSON.stringify({
          prompt: originalPrompt,
          history: historyPayload,
          connection_id: suggestion.connection_id || undefined,
        }),
      });
      if (!response.ok) {
        throw new Error(await readApiMessage(response, "No pude calcular la métrica recién creada."));
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("El servicio no devolvió una respuesta calculable.");

      const decoder = new TextDecoder();
      let answer = "";
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        signal.throwIfAborted();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";

        for (const rawEvent of events) {
          const line = rawEvent.trim();
          if (!line.startsWith("data: ")) continue;
          let event: { type?: string; content?: unknown };
          try {
            event = JSON.parse(line.substring(6));
          } catch {
            continue;
          }
          if (event.type === "chunk" && typeof event.content === "string") {
            answer += event.content;
          } else if (
            event.type === "semantic_context" &&
            event.content &&
            typeof event.content === "object" &&
            !Array.isArray(event.content)
          ) {
            setMessages((previous) =>
              previous.map((message) =>
                message.id === messageId
                  ? { ...message, semanticContext: event.content as Record<string, unknown> }
                  : message
              )
            );

          } else if (event.type === "metric_suggestion") {
            throw new Error("La métrica se creó, pero todavía no quedó disponible para consultarla.");
          } else if (event.type === "error") {
            throw new Error(typeof event.content === "string" ? event.content : "No pude calcular la nueva métrica.");
          }
        }
      }

      const calculatedAnswer = answer.trim() || "La métrica se creó, pero el servicio no devolvió un valor.";
      setMessages((previous) =>
        previous.map((message) =>
          message.id === messageId && message.metricSuggestion
            ? {
                ...message,
                content: `${confirmation}\n\n${calculatedAnswer}`,
                metricSuggestion: { ...message.metricSuggestion, status: "approved", statusMessage: "" },
              }
            : message
        )
      );
      scheduleStreamingScroll();
    } catch (error) {
      if (signal.aborted) return;
      setMessages((previous) =>
        previous.map((message) =>
          message.id === messageId && message.metricSuggestion
            ? {
                ...message,
                content: `${confirmation}\n\n${getErrorMessage(error, "No pude calcular el resultado en este momento.")}`,
                metricSuggestion: { ...message.metricSuggestion, status: "approved", statusMessage: "" },
              }
            : message
        )
      );
    } finally {
      if (!signal.aborted) {
        setIsProcessing(false);
      }
    }
  };

  const handleMetricDraftAction = async (
    messageId: string,
    suggestion: MetricSuggestion,
    action: "approve" | "reject"
  ) => {
    if (action === "approve" && suggestion.requires_definition) {
      updateMetricSuggestion(messageId, {
        status: "error",
        statusMessage: "Primero describí cómo querés calcular esta métrica.",
      });
      return;
    }
    if (!suggestion.draft_id && action === "reject") {
      updateMetricSuggestion(messageId, {
        status: "rejected",
        statusMessage: "Entendido. No creé la métrica.",
      });
      return;
    }

    updateMetricSuggestion(messageId, {
      status: "saving",
      statusMessage: action === "approve" ? "Creando la métrica..." : "Descartando la propuesta...",
    });

    try {
      const auth = await getSupabaseAuthHeaders();
      if (!auth.headers.Authorization) {
        updateMetricSuggestion(messageId, {
          status: "error",
          statusMessage: "Necesitás iniciar sesión para modificar el modelo semántico.",
        });
        return;
      }

      if (!suggestion.draft_id) {
        const response = await fetch(`${apiBaseUrl}/semantic-model/metrics`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...auth.headers },
          body: JSON.stringify({
            name: suggestion.name,
            description: suggestion.description,
            expression: suggestion.expression,
            format: suggestion.format || "number",
            created_by_ai: true,
            connection_id: suggestion.connection_id,
          }),
        });
        if (!response.ok) {
          updateMetricSuggestion(messageId, {
            status: "error",
            statusMessage: await readApiMessage(response, "No pude crear la métrica propuesta."),
          });
          return;
        }
        const metric = await response.json().catch(() => ({}));
        await answerOriginalQuestion(messageId, suggestion, metric?.name || suggestion.name);
        return;
      }

      const response = await fetch(`${apiBaseUrl}/semantic-metrics/drafts/${suggestion.draft_id}/${action}`, {
        method: "POST",
        headers: auth.headers,
      });
      if (!response.ok) {
        updateMetricSuggestion(messageId, {
          status: "error",
          statusMessage: await readApiMessage(response, "No pude actualizar la propuesta."),
        });
        return;
      }
      const payload = await response.json().catch(() => ({}));
      const metricName = payload?.metric?.name || suggestion.name;
      if (action === "approve") {
        await answerOriginalQuestion(messageId, suggestion, metricName);
      } else {
        updateMetricSuggestion(messageId, {
          status: "rejected",
          statusMessage: "Entendido. No creé la métrica.",
        });
      }
    } catch {
      updateMetricSuggestion(messageId, {
        status: "error",
        statusMessage: "No pude actualizar la propuesta porque el servicio no está disponible.",
      });
    }
  };

  const looksLikeMetricExpression = (value: string) =>
    /@/.test(value) || /\b(?:sum|avg|count|count_distinct|date_diff)\s*\(/i.test(value);

  const handleCreateAlternativeMetric = async (messageId: string, suggestion: MetricSuggestion) => {
    const alternative = (suggestion.alternativeExpression || "").trim();
    if (!alternative) return;

    updateMetricSuggestion(messageId, {
      status: "saving",
      statusMessage: "Preparando tu forma de calcularla...",
    });

    try {
      const auth = await getSupabaseAuthHeaders();
      if (!auth.headers.Authorization) {
        updateMetricSuggestion(messageId, {
          status: "error",
          statusMessage: "Necesitás iniciar sesión para modificar el modelo semántico.",
        });
        return;
      }

      let expression = alternative;
      let description = suggestion.description;
      let format = suggestion.format || "number";
      if (!looksLikeMetricExpression(alternative)) {
        const response = await fetch(`${apiBaseUrl}/semantic-model/metrics/suggest`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...auth.headers },
          body: JSON.stringify({
            name: suggestion.name,
            goal: alternative,
            connection_id: suggestion.connection_id,
          }),
        });
        if (!response.ok) {
          updateMetricSuggestion(messageId, {
            status: "error",
            statusMessage: await readApiMessage(response, "No pude convertir esa alternativa en una fórmula válida."),
          });
          return;
        }
        const generated = await response.json();
        expression = generated.expression || expression;
        description = generated.description || description;
        format = generated.format || format;
      }

      const response = await fetch(`${apiBaseUrl}/semantic-model/metrics`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth.headers },
        body: JSON.stringify({
          name: suggestion.name,
          description,
          expression,
          format,
          created_by_ai: true,
          connection_id: suggestion.connection_id,
        }),
      });
      if (!response.ok) {
        updateMetricSuggestion(messageId, {
          status: "error",
          statusMessage: await readApiMessage(response, "No pude guardar la definición alternativa."),
        });
        return;
      }

      const metric = await response.json().catch(() => ({}));
      await answerOriginalQuestion(
        messageId,
        { ...suggestion, expression, description, format },
        metric?.name || suggestion.name
      );
    } catch {
      updateMetricSuggestion(messageId, {
        status: "error",
        statusMessage: "No pude guardar la alternativa porque el servicio no está disponible.",
      });
    }
  };

  const handleAcceptMetricOption = (messageId: string, suggestion: MetricSuggestion) => {
    if (suggestion.selectedOption === "approve") {
      void handleMetricDraftAction(messageId, suggestion, "approve");
    } else if (suggestion.selectedOption === "reject") {
      void handleMetricDraftAction(messageId, suggestion, "reject");
    } else if (suggestion.selectedOption === "custom") {
      void handleCreateAlternativeMetric(messageId, suggestion);
    }
  };

  const handleSendMessage = async (prompt: string, starter?: "weekly_sales" | "churn") => {
    if (sessionAbortRef.current?.signal.aborted) return;
    const controller = sessionAbortRef.current ?? new AbortController();
    sessionAbortRef.current = controller;
    const signal = controller.signal;
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
      const historyPayload = buildChatHistory(messages);

      const connectionId = window.localStorage.getItem("nyro_active_connection_id");
      const auth = await getSupabaseAuthHeaders();
      const canUseSemanticConnection = Boolean(connectionId && auth.token);

      const res = await fetch(`${apiBaseUrl}/chat/`, {
        signal,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...auth.headers,
        },
        body: JSON.stringify({
          prompt,
          history: historyPayload,
          starter,
          connection_id: canUseSemanticConnection ? connectionId : undefined,
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
          signal.throwIfAborted();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n\n");
          buffer = lines.pop() || "";

          for (const rawLine of lines) {
            const line = rawLine.trim();
            if (!line.startsWith("data: ")) continue;

            const dataStr = line.substring(6);
            if (!dataStr) continue;

            let data: {
              type?: string;
              content?: unknown;
            };
            try {
              data = JSON.parse(dataStr);
            } catch (e) {
              console.error("Error parsing stream data:", e);
              continue;
            }

            if (data.type === "chunk" && typeof data.content === "string") {
              fullContent += data.content;

              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === astMsgId
                    ? { ...msg, content: fullContent }
                    : msg
                )
              );
              scheduleStreamingScroll();
            } else if (
              data.type === "semantic_context" &&
              data.content &&
              typeof data.content === "object" &&
              !Array.isArray(data.content)
            ) {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === astMsgId
                    ? { ...msg, semanticContext: data.content as Record<string, unknown> }
                    : msg
                )
              );

            } else if (data.type === "metric_suggestion" && data.content && typeof data.content === "object") {
              const payload = data.content as {
                message?: string;
                suggestion?: Partial<MetricSuggestion>;
              };
              const suggestion = payload.suggestion;
              if (
                !suggestion?.name ||
                !suggestion.proposed_calculation ||
                (!suggestion.expression && !suggestion.requires_definition)
              ) {
                throw new Error("El servicio devolvió una propuesta de métrica incompleta.");
              }
              const metricSuggestion: MetricSuggestion = {
                description: suggestion.description || "",
                format: suggestion.format || "number",
                connection_id: suggestion.connection_id,
                draft_id: suggestion.draft_id,
                name: suggestion.name,
                expression: suggestion.expression || "",
                proposed_calculation: suggestion.proposed_calculation,
                requires_definition: Boolean(suggestion.requires_definition),
                status: "pending",
                statusMessage: "",
                alternativeExpression: "",
                selectedOption: suggestion.requires_definition ? "custom" : undefined,
                sourcePrompt: prompt,
              };
              fullContent = payload.message || "Detecté que esta métrica no existe en el modelo semántico. ¿Querés que la cree?";
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === astMsgId
                    ? {
                        ...msg,
                        content: fullContent,
                        isLoading: false,
                        metricSuggestion,
                      }
                    : msg
                )
              );
              scheduleStreamingScroll();
            } else if (data.type === "error") {
              throw new Error(typeof data.content === "string" ? data.content : "El servicio no pudo responder.");
            }
          }
        }
      }

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === astMsgId
            ? {
                ...msg,
                content: msg.content || "No recibí una respuesta del servicio. Probá repetir la consulta o revisar la conexión activa.",
                isLoading: false,
              }
            : msg
        )
      );
      scrollToBottom("smooth");

    } catch (error: unknown) {
      if (signal.aborted) return;
      console.error(error);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === astMsgId
            ? { ...msg, content: `Error: ${getErrorMessage(error)}`, isLoading: false }
            : msg
        )
      );
    } finally {
      if (!signal.aborted) {
        setIsProcessing(false);
      }
    }
  };

  const renderMessageBody = (message: Message) => {
    if (message.role === "user") {
      return <span className="whitespace-pre-wrap text-[15px] leading-7 text-[#f7f7f2]">{message.content}</span>;
    }

    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className="mb-3 mt-1 text-lg font-semibold leading-7 text-[#f7f7f2]">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-2 mt-1 text-base font-semibold leading-6 text-[#f7f7f2]">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-2 mt-1 text-sm font-semibold leading-6 text-[#f7f7f2]">{children}</h3>,
          p: ({ children }) => <p className="mb-3 text-[15px] leading-7 text-[#f7f7f2] last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 text-[15px] leading-7 text-[#f7f7f2] last:mb-0">{children}</ul>,
          ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 text-[15px] leading-7 text-[#f7f7f2] last:mb-0">{children}</ol>,
          li: ({ children }) => <li className="text-[#f7f7f2]">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold text-[#ffffff]">{children}</strong>,
          a: ({ children, href }) => (
            <a href={href} className="font-medium text-[#e9fbff] underline decoration-white/30 underline-offset-4 hover:text-[#ffffff]">
              {children}
            </a>
          ),
          code: ({ children }) => <code className="rounded-md bg-white/10 px-1.5 py-0.5 text-[0.9em] text-[#f9faf7]">{children}</code>,
          pre: ({ children }) => <pre className="mb-3 overflow-x-auto rounded-xl border border-white/10 bg-black/30 p-3 text-left text-sm text-[#f9faf7]">{children}</pre>,
        }}
      >
        {message.content}
      </ReactMarkdown>
    );
  };

  const renderMetricSuggestion = (message: Message) => {
    const suggestion = message.metricSuggestion;
    if (!suggestion) return null;

    const status = suggestion.status || "pending";
    const isBusy = status === "saving";
    const isClosed = status === "approved" || status === "rejected";
    const selectedOption = suggestion.selectedOption;
    const canAccept = Boolean(
      selectedOption &&
      !(selectedOption === "approve" && suggestion.requires_definition) &&
      (selectedOption !== "custom" || (suggestion.alternativeExpression || "").trim())
    );
    const statusClasses =
      status === "approved"
        ? "border-emerald-100/20 bg-emerald-300/15 text-emerald-50"
        : status === "rejected"
          ? "border-white/10 bg-black/15 text-[#dfe7df]/75"
          : status === "error"
            ? "border-red-200/25 bg-red-300/15 text-red-50"
            : "border-white/10 bg-black/15 text-[#dfe7df]/75";
    const optionClasses = (option: MetricSuggestion["selectedOption"]) => [
      "flex w-full items-center gap-3 rounded-xl border px-3.5 py-3 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 disabled:cursor-not-allowed disabled:opacity-60",
      selectedOption === option
        ? "border-white/35 bg-white/15 text-white"
        : "border-white/15 bg-black/15 text-[#eef5ed] hover:bg-white/10",
    ].join(" ");

    if (isClosed && !suggestion.statusMessage) return null;

    return (
      <div
        className="mt-4 border-t border-white/15 pt-4"
        role="group"
        aria-label={`Crear la métrica ${suggestion.name}`}
      >
        {!isClosed ? (
          <>
            <div className="space-y-2">
              {!suggestion.requires_definition ? (
                <button
                  type="button"
                  onClick={() => updateMetricSuggestion(message.id, { selectedOption: "approve", statusMessage: "" })}
                  disabled={isBusy}
                  className={optionClasses("approve")}
                >
                  <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${selectedOption === "approve" ? "border-white bg-white text-[#24312e]" : "border-white/35"}`}>
                    {selectedOption === "approve" ? <Check size={13} strokeWidth={2.8} /> : null}
                  </span>
                  <span className="font-medium">Sí, crear la métrica</span>
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => updateMetricSuggestion(message.id, { selectedOption: "reject", statusMessage: "" })}
                disabled={isBusy}
                className={optionClasses("reject")}
              >
                <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${selectedOption === "reject" ? "border-white bg-white text-[#24312e]" : "border-white/35"}`}>
                  {selectedOption === "reject" ? <Check size={13} strokeWidth={2.8} /> : null}
                </span>
                <span className="font-medium">No crearla</span>
              </button>

              <div className={`overflow-hidden rounded-xl border transition-colors ${selectedOption === "custom" ? "border-white/35 bg-white/15" : "border-white/15 bg-black/15"}`}>
                <button
                  type="button"
                  onClick={() => updateMetricSuggestion(message.id, { selectedOption: "custom", statusMessage: "" })}
                  disabled={isBusy}
                  className="flex w-full items-center gap-3 px-3.5 py-3 text-left text-sm text-[#eef5ed] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white/70 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${selectedOption === "custom" ? "border-white bg-white text-[#24312e]" : "border-white/35 text-white/75"}`}>
                    <Pencil size={11} strokeWidth={2.4} />
                  </span>
                  <span className="font-medium">Describir otro cálculo de métrica</span>
                </button>
                {selectedOption === "custom" ? (
                  <div className="px-3.5 pb-3.5 pl-11">
                    <label htmlFor={`metric-alternative-${message.id}`} className="sr-only">
                      Describí otro cálculo de métrica
                    </label>
                    <textarea
                      id={`metric-alternative-${message.id}`}
                      autoFocus
                      value={suggestion.alternativeExpression || ""}
                      onChange={(event) => updateMetricSuggestion(message.id, { alternativeExpression: event.target.value })}
                      placeholder={
                        suggestion.requires_definition
                          ? "Describí qué fechas, eventos o condiciones debería usar..."
                          : "Ej.: promediar sólo proveedores activos..."
                      }
                      rows={2}
                      disabled={isBusy}
                      className="w-full resize-none rounded-lg border border-white/20 bg-black/25 px-3 py-2 text-sm leading-5 text-[#f7f7f2] outline-none placeholder:text-[#dfe7df]/45 focus:border-white/35 focus:ring-2 focus:ring-white/15 disabled:cursor-not-allowed disabled:opacity-60"
                    />
                  </div>
                ) : null}
              </div>
            </div>

            <div className="mt-3 flex justify-end">
              <button
                type="button"
                onClick={() => handleAcceptMetricOption(message.id, suggestion)}
                disabled={isBusy || !canAccept}
                className="inline-flex min-w-28 items-center justify-center gap-2 rounded-lg bg-[#f7f7f2] px-5 py-2.5 text-sm font-semibold text-[#17201e] transition-colors hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/80 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {isBusy ? <Loader2 size={15} className="animate-spin" /> : null}
                {isBusy ? "Procesando..." : "Aceptar"}
              </button>
            </div>
          </>
        ) : null}

        {suggestion.statusMessage ? (
          <div className={`mt-3 flex items-start gap-2 rounded-xl border px-3 py-2.5 text-xs leading-5 ${statusClasses}`} role="status">
            {isBusy ? (
              <Loader2 size={14} className="mt-0.5 shrink-0 animate-spin" />
            ) : status === "approved" ? (
              <Check size={14} className="mt-0.5 shrink-0" />
            ) : status === "rejected" ? (
              <X size={14} className="mt-0.5 shrink-0" />
            ) : null}
            <span>{suggestion.statusMessage}</span>
          </div>
        ) : null}
      </div>
    );
  };

  return (
    <div className="relative flex h-full flex-1 flex-col overflow-hidden text-[#f7f7f2]" style={CHAT_BACKGROUND_STYLE}>
      <div aria-hidden className="pointer-events-none absolute inset-0 bg-black/[0.06]" />
      <div aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-[62%] opacity-50 mix-blend-multiply" style={DITHER_STYLE} />

      <header
        className={`pointer-events-none absolute left-0 right-0 top-0 z-20 flex items-center justify-between px-4 md:px-6 ${isSidebarMode ? "py-4" : "py-5 md:py-6"}`}
        style={TOP_FADE_STYLE}
      >
        <div className="pointer-events-auto">
          <button
            type="button"
            className="flex items-center gap-2 rounded-full bg-black/20 px-3 py-2 text-[#f7f7f2] shadow-lg shadow-black/10 backdrop-blur-xl transition-colors hover:bg-black/28 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f7f7f2]/80 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
            aria-label={isSidebarMode ? "Opciones del chat" : "Opciones de BI AI"}
          >
            <span className="text-sm font-semibold">{isSidebarMode ? "Nuevo chat" : "BI AI"}</span>
            <ChevronDown size={15} className="text-[#dfe7df]/80" />
          </button>
        </div>

        <div className="pointer-events-auto flex items-center gap-2">
          {!isSidebarMode && (
            <button
              type="button"
              aria-label="Buscar en el chat. Atajo Q barra"
              className="flex h-10 items-center gap-2 rounded-full border border-white/15 bg-black/25 px-3 text-sm text-[#f7f7f2] shadow-lg shadow-black/10 backdrop-blur-xl transition-colors hover:bg-black/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f7f7f2]/80 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
            >
              <Search size={16} />
              <span className="flex items-center gap-1 text-xs text-[#dfe7df]/70">
                <kbd className="rounded-md bg-white/10 px-1.5 py-0.5 font-mono">Q</kbd>
                <span>/</span>
              </span>
            </button>
          )}

        </div>
      </header>

      <div className={`relative z-10 flex-1 overflow-y-auto ${isSidebarMode ? "pb-[136px] pt-20 md:pt-24" : "pb-[156px] pt-28 md:pt-32"}`}>
        {messages.length === 0 ? (
          isSidebarMode ? (
            <div className="mx-auto w-full px-4 py-5 md:px-5">
              <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#eef5ed]/70">
                Preguntas sugeridas
              </p>
              <div className="flex flex-col gap-3">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion.title}
                    onClick={() => handleSendMessage(suggestion.prompt, suggestion.starter)}
                    type="button"
                    className="min-h-[96px] rounded-2xl border border-white/15 bg-black/30 p-4 text-left shadow-xl shadow-black/20 backdrop-blur-2xl transition-all duration-300 hover:-translate-y-0.5 hover:border-white/25 hover:bg-black/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f7f7f2]/70 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
                  >
                    <h4 className="text-sm font-semibold leading-5 text-[#f7f7f2]">{suggestion.title}</h4>
                    <p className="mt-1 text-xs leading-5 text-[#dfe7df]/75">{suggestion.description}</p>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto flex min-h-full w-full max-w-[880px] flex-col items-center justify-center px-5 pb-8 text-center">
              <h1 className="max-w-[720px] text-4xl font-semibold leading-tight tracking-normal text-[#f7f7f2] md:text-5xl">
                Hola de nuevo{userName ? `, ${userName}` : ""}!
              </h1>
              <p className="mt-4 max-w-none whitespace-nowrap text-sm leading-6 text-[#eef5ed]/72 md:text-base">
                Felicidades: acabas de ahorrarte tres reuniones interminables con solo estar acá.
              </p>

              <div className="mt-9 grid w-full grid-cols-1 gap-4 md:grid-cols-3">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion.title}
                    onClick={() => handleSendMessage(suggestion.prompt, suggestion.starter)}
                    type="button"
                    className="min-h-[132px] rounded-2xl border border-white/15 bg-black/30 p-5 text-left shadow-2xl shadow-black/20 backdrop-blur-2xl transition-all duration-300 hover:-translate-y-0.5 hover:border-white/25 hover:bg-black/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f7f7f2]/70 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
                  >
                    <h4 className="text-sm font-semibold leading-5 text-[#f7f7f2]">{suggestion.title}</h4>
                    <p className="mt-2 text-xs leading-5 text-[#dfe7df]/75">{suggestion.description}</p>
                  </button>
                ))}
              </div>
            </div>
          )
        ) : (
          <div className={`mx-auto flex w-full flex-col gap-4 pb-6 md:gap-5 ${isSidebarMode ? "px-4 md:px-5" : "max-w-[860px] px-4 md:px-6"}`}>
            {messages.map((message) => {
              const isUser = message.role === "user";
              const isThinking = message.role === "assistant" && message.isLoading && message.content === "";

              if (isThinking) {
                return (
                  <div
                    key={message.id}
                    className={[
                      "mr-auto flex items-center gap-3 text-sm font-medium text-[#eef5ed]/80",
                      isSidebarMode ? "w-fit max-w-[92%] px-4 py-3.5" : "w-fit max-w-[82%] px-5 py-4 md:px-6 md:py-5",
                    ].join(" ")}
                  >
                    <MagneticDots />
                    <span>Analizando datos...</span>
                  </div>
                );
              }

              return (
                <article
                  key={message.id}
                  className={[
                    "relative overflow-hidden rounded-2xl border shadow-2xl [backface-visibility:hidden] [contain:paint]",
                    isSidebarMode ? "w-fit max-w-[92%] px-4 py-3.5" : "w-fit max-w-[82%] px-5 py-4 md:px-6 md:py-5",
                    isUser
                      ? "ml-auto border-white/20 bg-[rgba(31,42,39,0.82)] shadow-black/25"
                      : "mr-auto border-white/15 bg-[rgba(32,52,48,0.78)] shadow-black/20",
                  ].join(" ")}
                >
                  <div>{renderMessageBody(message)}</div>
                  {!isUser ? renderMetricSuggestion(message) : null}
                </article>
              );
            })}
            <div ref={bottomRef} className="h-4" />
          </div>
        )}
      </div>

      <div
        className={`pointer-events-none absolute bottom-0 left-0 right-0 z-20 px-3 pt-12 md:px-5 ${isSidebarMode ? "pb-4" : "pb-5 md:pb-6"}`}
        style={BOTTOM_FADE_STYLE}
      >
        <div className="pointer-events-auto">
          <ChatInput
            onSend={handleSendMessage}
            isLoading={isProcessing}
            compact={isSidebarMode}
            variant="glass"
          />
        </div>
      </div>
    </div>
  );
};
