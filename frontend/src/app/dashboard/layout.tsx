import { AppIslandLayout } from "@/components/layout/AppIslandLayout";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AppIslandLayout>{children}</AppIslandLayout>;
}
