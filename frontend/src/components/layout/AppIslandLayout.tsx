import type { ReactNode } from "react";

import Sidebar from "@/components/chat/Sidebar";
import { cn } from "@/lib/utils";

type AppIslandLayoutProps = {
  children: ReactNode;
  rootClassName?: string;
};

export function AppIslandLayout({ children, rootClassName }: AppIslandLayoutProps) {
  return (
    <div
      className={cn(
        "flex h-dvh w-full overflow-hidden bg-black text-[#f7f7f2] md:h-screen",
        rootClassName,
      )}
    >
      <Sidebar />
      <main className="min-h-0 min-w-0 flex h-full flex-1 flex-col bg-black p-1.5 pb-24 md:pb-1.5 md:pl-0">
        <div className="relative flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden rounded-[28px] bg-black shadow-[0_24px_90px_rgba(0,0,0,0.42)] [clip-path:inset(0_round_28px)] md:rounded-[32px] md:[clip-path:inset(0_round_32px)]">
          {children}
        </div>
      </main>
    </div>
  );
}
