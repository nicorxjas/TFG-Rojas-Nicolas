"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

type CompanyData = {
  companyName: string;
  sector: string;
  details: string;
};

type CompanyRow = {
  company_name: string | null;
  sector: string | null;
  details: string | null;
};

export default function EmpresaSettingsPage() {
  const supabase = createClient();
  const [userId, setUserId] = useState<string | null>(null);
  const [company, setCompany] = useState<CompanyData>({
    companyName: "",
    sector: "",
    details: "",
  });
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  useEffect(() => {
    const fetchCompany = async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return;
      setUserId(user.id);

      const { data } = await supabase
        .from("company_settings")
        .select("company_name, sector, details")
        .eq("id", user.id)
        .maybeSingle<CompanyRow>();

      setCompany({
        companyName: data?.company_name ?? "",
        sector: data?.sector ?? "",
        details: data?.details ?? "",
      });
    };

    fetchCompany();
  }, [supabase]);

  const handleSaveCompany = async () => {
    if (!userId) return;

    setIsSaving(true);
    setSaveMessage(null);

    const { error } = await supabase
      .from("company_settings")
      .upsert({
        id: userId,
        company_name: company.companyName.trim(),
        sector: company.sector.trim(),
        details: company.details.trim(),
      });

    setIsSaving(false);

    if (error) {
      setSaveMessage(`No se pudo guardar: ${error.message}`);
      return;
    }

    setSaveMessage("Empresa guardada");
  };

  return (
    <>
      <section className="flex-1 overflow-y-auto bg-[#0a0a0b]">
        <div className="mx-auto w-full max-w-[760px] px-5 py-10 md:py-16">
          <h1 className="mb-8 text-2xl font-semibold text-zinc-50">Empresa</h1>

          <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/45">
            <div className="grid min-h-[64px] grid-cols-[1fr_minmax(220px,280px)] items-center gap-4 border-b border-zinc-800 px-4">
              <span className="text-sm font-semibold text-zinc-100">Empresa</span>
              <input
                value={company.companyName}
                onChange={(e) => setCompany((current) => ({ ...current, companyName: e.target.value }))}
                placeholder="Nombre de la empresa"
                className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm font-medium text-zinc-100 outline-none transition-colors placeholder:text-zinc-600 focus:border-zinc-600"
              />
            </div>

            <div className="grid min-h-[64px] grid-cols-[1fr_minmax(220px,280px)] items-center gap-4 border-b border-zinc-800 px-4">
              <span className="text-sm font-semibold text-zinc-100">Sector</span>
              <input
                value={company.sector}
                onChange={(e) => setCompany((current) => ({ ...current, sector: e.target.value }))}
                placeholder="Ej. Retail, SaaS, Manufactura"
                className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm font-medium text-zinc-100 outline-none transition-colors placeholder:text-zinc-600 focus:border-zinc-600"
              />
            </div>

            <div className="space-y-3 px-4 py-4">
              <div>
                <span className="block text-sm font-semibold text-zinc-100">Detalles</span>
                <span className="mt-0.5 block text-sm text-zinc-500">Contexto operativo, particularidades del negocio o instrucciones relevantes.</span>
              </div>
              <textarea
                value={company.details}
                onChange={(e) => setCompany((current) => ({ ...current, details: e.target.value }))}
                placeholder="Agrega detalles..."
                className="min-h-[220px] w-full resize-none rounded-xl border border-zinc-800 bg-zinc-950 px-4 py-4 font-sans text-sm leading-relaxed text-zinc-100 outline-none transition-colors placeholder:text-zinc-600 focus:border-zinc-600"
              />
            </div>
          </div>

          <div className="mt-4 flex items-center justify-end gap-3">
            {saveMessage && (
              <span className={`text-sm ${saveMessage.startsWith("No se pudo") ? "text-rose-400" : "text-zinc-500"}`}>
                {saveMessage}
              </span>
            )}
            <button
              onClick={handleSaveCompany}
              disabled={isSaving || !userId}
              className="rounded-full bg-zinc-100 px-4 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSaving ? "Guardando..." : "Guardar cambios"}
            </button>
          </div>
        </div>
      </section>
    </>
  );
}
