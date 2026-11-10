import { AppIslandLayout } from "@/components/layout/AppIslandLayout";

export default function ModeloSemanticoLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AppIslandLayout>{children}</AppIslandLayout>;
}
