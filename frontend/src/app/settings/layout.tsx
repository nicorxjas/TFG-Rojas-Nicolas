import { SettingsNav } from "@/components/settings/SettingsNav";

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-dvh w-full flex-col bg-zinc-950 text-white md:h-screen md:flex-row">
      <SettingsNav />
      <main className="flex min-h-0 flex-1 bg-[#0a0a0b]">
        {children}
      </main>
    </div>
  );
}
