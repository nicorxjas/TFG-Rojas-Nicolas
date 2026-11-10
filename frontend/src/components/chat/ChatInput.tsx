"use client";

import TextareaAutosize from "react-textarea-autosize";
import { ArrowUp } from "lucide-react";
import { useState } from "react";

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading: boolean;
  placeholder?: string;
  variant?: "glass" | "dark";
  compact?: boolean;
}

export default function ChatInput({
  onSend,
  isLoading,
  placeholder,
  variant = "glass",
  compact = false,
}: ChatInputProps) {
  const [input, setInput] = useState("");
  const isGlass = variant === "glass";

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    onSend(input);
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as unknown as React.FormEvent);
    }
  };

  return (
    <div className={`mx-auto w-full ${compact ? "max-w-full px-0 py-1" : "max-w-[820px] px-3 py-1.5 pb-2 md:px-4"}`}>
      <form
        onSubmit={handleSubmit}
        className={[
          "relative flex min-h-[60px] w-full items-end gap-2 rounded-[24px] border p-2 transition-all duration-200",
          isGlass
            ? "border-white/15 bg-black/35 shadow-[0_20px_70px_rgba(0,0,0,0.28)] backdrop-blur-2xl focus-within:border-white/35 focus-within:ring-2 focus-within:ring-white/25"
            : "border-[#27272a] bg-[#111113] focus-within:border-[#3f3f46] focus-within:ring-2 focus-within:ring-[#52525b]/30",
        ].join(" ")}
      >
        <div className="flex-1 py-2 pl-3 pr-12 md:pl-4">
          <TextareaAutosize
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            minRows={1}
            maxRows={6}
            placeholder={placeholder || "Preguntale a BI AI sobre tus datos..."}
            className={[
              "max-h-40 w-full resize-none overflow-y-auto bg-transparent p-0 text-[15px] leading-6 outline-none",
              isGlass
                ? "text-[#f7f7f2] placeholder:text-[#dfe7df]/60"
                : "text-[#f4f4f5] placeholder:text-[#71717a]",
            ].join(" ")}
            style={{ padding: 0 }}
          />
        </div>

        <button
          type="submit"
          disabled={!input.trim() || isLoading}
          aria-label={isLoading ? "Synthesis esta procesando" : "Enviar mensaje"}
          className={[
            "absolute bottom-3 right-3 flex h-8 w-8 shrink-0 items-center justify-center rounded-full shadow-sm transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f7f7f2]/80 focus-visible:ring-offset-2 focus-visible:ring-offset-black disabled:cursor-not-allowed disabled:opacity-50",
            isGlass
              ? "bg-[#f7f7f2] text-[#101110] hover:bg-white"
              : "bg-[#e4e4e7] text-[#09090b] hover:bg-white",
          ].join(" ")}
        >
          {isLoading ? (
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#101110]/30 border-t-[#101110]" />
          ) : (
            <ArrowUp size={18} />
          )}
        </button>
      </form>

      <div className="text-center mt-1.5">
        <p className={isGlass ? "text-[10px] text-[#eef5ed]/65 md:text-xs" : "text-[10px] text-[#71717a] md:text-xs"}>
          BI AI puede equivocarse; revisa los datos clave.
        </p>
      </div>
    </div>
  );
}
