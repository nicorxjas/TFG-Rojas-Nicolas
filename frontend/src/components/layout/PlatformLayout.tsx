"use client";

import { useEffect, useState } from "react";
import { ChatSidebar } from "../chat/ChatSidebar";
import { NEW_CHAT_EVENT } from "@/lib/chat-events";

export const PlatformLayout = () => {
  const [chatSession, setChatSession] = useState(0);

  useEffect(() => {
    const resetChat = () => setChatSession((session) => session + 1);
    window.addEventListener(NEW_CHAT_EVENT, resetChat);
    return () => window.removeEventListener(NEW_CHAT_EVENT, resetChat);
  }, []);

  return (
    <div className="relative flex h-full w-full overflow-hidden bg-[#A6B5A8]">
      <ChatSidebar key={chatSession} />
    </div>
  );
};
