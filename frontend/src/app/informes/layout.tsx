import { AppIslandLayout } from "@/components/layout/AppIslandLayout";

export default function InformesLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AppIslandLayout rootClassName="antialiased selection:bg-zinc-800">
      {children}
    </AppIslandLayout>
  );
}
