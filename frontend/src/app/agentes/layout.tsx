import { AppIslandLayout } from "@/components/layout/AppIslandLayout";

export default function AgentesLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AppIslandLayout>{children}</AppIslandLayout>;
}
