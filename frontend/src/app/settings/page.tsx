"use client";

import { useEffect, useMemo, useState } from "react";
import { Edit2 } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

type ProfileData = {
  email: string;
  fullName: string;
  title: string;
  username: string;
  avatarUrl?: string;
};

type ProfileRow = {
  email: string | null;
  full_name: string | null;
  title: string | null;
  username: string | null;
  avatar_url: string | null;
};

function getInitials(profile: ProfileData) {
  const source = profile.fullName || profile.username || profile.email;
  const parts = source.split(/[\s@._-]+/).filter(Boolean);
  return (parts[0]?.[0] ?? "U").concat(parts[1]?.[0] ?? "").toUpperCase();
}

export default function SettingsPage() {
  const supabase = createClient();
  const [userId, setUserId] = useState<string | null>(null);
  const [profile, setProfile] = useState<ProfileData>({
    email: "",
    fullName: "",
    title: "",
    username: "",
  });
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  useEffect(() => {
    const fetchProfile = async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return;
      setUserId(user.id);

      const metadata = {
        ...user.user_metadata,
        ...user.app_metadata,
      } as Record<string, string | undefined>;

      const email = user.email ?? "";
      const fallbackUsername = email.split("@")[0] ?? "";
      const { data: profileRow } = await supabase
        .from("profiles")
        .select("email, full_name, title, username, avatar_url")
        .eq("id", user.id)
        .maybeSingle<ProfileRow>();

      setProfile({
        email: profileRow?.email ?? email,
        fullName: profileRow?.full_name ?? metadata.full_name ?? metadata.name ?? "",
        title: profileRow?.title ?? metadata.title ?? metadata.role ?? "",
        username: profileRow?.username ?? metadata.username ?? fallbackUsername,
        avatarUrl: profileRow?.avatar_url ?? metadata.avatar_url,
      });
    };

    fetchProfile();
  }, [supabase]);

  const initials = useMemo(() => getInitials(profile), [profile]);

  const handleSaveProfile = async () => {
    if (!userId) return;

    setIsSaving(true);
    setSaveMessage(null);

    const { error } = await supabase
      .from("profiles")
      .upsert({
        id: userId,
        email: profile.email,
        full_name: profile.fullName.trim(),
        title: profile.title.trim(),
        username: profile.username.trim(),
        avatar_url: profile.avatarUrl ?? null,
      });

    setIsSaving(false);

    if (error) {
      setSaveMessage(`No se pudo guardar: ${error.message}`);
      return;
    }

    setSaveMessage("Perfil guardado");
  };

  return (
    <>
      <section className="flex-1 overflow-y-auto bg-[#0a0a0b]">
        <div className="mx-auto w-full max-w-[760px] px-5 py-10 md:py-16">
          <h1 className="mb-8 text-2xl font-semibold text-zinc-50">Perfil</h1>

          <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/45">
            <div className="grid min-h-[64px] grid-cols-[1fr_auto] items-center gap-4 border-b border-zinc-800 px-4">
              <span className="text-sm font-semibold text-zinc-100">Foto de perfil</span>
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-orange-500 text-sm font-semibold text-white">
                {profile.avatarUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={profile.avatarUrl} alt="" className="h-full w-full rounded-full object-cover" />
                ) : (
                  initials
                )}
              </div>
            </div>

            <div className="grid min-h-[64px] grid-cols-[1fr_minmax(220px,280px)] items-center gap-4 border-b border-zinc-800 px-4">
              <span className="text-sm font-semibold text-zinc-100">Email</span>
              <div className="flex items-center justify-end gap-3">
                <span className="truncate text-sm font-semibold text-zinc-100">{profile.email || "Sin email"}</span>
                <button className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-zinc-500">
                  <Edit2 size={12} />
                </button>
              </div>
            </div>

            <div className="grid min-h-[64px] grid-cols-[1fr_minmax(220px,280px)] items-center gap-4 border-b border-zinc-800 px-4">
              <span className="text-sm font-semibold text-zinc-100">Nombre completo</span>
              <input
                value={profile.fullName}
                onChange={(e) => setProfile((current) => ({ ...current, fullName: e.target.value }))}
                placeholder="Nombre completo"
                className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm font-medium text-zinc-100 outline-none transition-colors placeholder:text-zinc-600 focus:border-zinc-600"
              />
            </div>

            <div className="grid min-h-[64px] grid-cols-[1fr_minmax(220px,280px)] items-center gap-4 border-b border-zinc-800 px-4">
              <div>
                <span className="block text-sm font-semibold text-zinc-100">Cargo</span>
                <span className="mt-0.5 block text-sm text-zinc-500">Tu puesto o rol</span>
              </div>
              <input
                value={profile.title}
                onChange={(e) => setProfile((current) => ({ ...current, title: e.target.value }))}
                placeholder="Ej. Software engineer"
                className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm font-medium text-zinc-100 outline-none transition-colors placeholder:text-zinc-600 focus:border-zinc-600"
              />
            </div>

            <div className="grid min-h-[64px] grid-cols-[1fr_minmax(220px,280px)] items-center gap-4 px-4">
              <div>
                <span className="block text-sm font-semibold text-zinc-100">Nombre de usuario</span>
                <span className="mt-0.5 block text-sm text-zinc-500">Una palabra, como un apodo o nombre</span>
              </div>
              <input
                value={profile.username}
                onChange={(e) => setProfile((current) => ({ ...current, username: e.target.value }))}
                placeholder="usuario"
                className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm font-medium text-zinc-100 outline-none transition-colors placeholder:text-zinc-600 focus:border-zinc-600"
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
              onClick={handleSaveProfile}
              disabled={isSaving || !userId}
              className="rounded-full bg-zinc-100 px-4 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSaving ? "Guardando..." : "Guardar cambios"}
            </button>
          </div>

          <h2 className="mb-5 mt-12 text-base font-semibold text-zinc-100">Acceso al espacio de trabajo</h2>
          <div className="grid min-h-[64px] grid-cols-[1fr_auto] items-center gap-4 rounded-xl border border-zinc-800 bg-zinc-900/45 px-4">
            <span className="text-sm font-semibold text-zinc-500">Quitarte del espacio de trabajo</span>
            <button className="text-sm font-semibold text-zinc-500 transition-colors hover:text-zinc-200">
              Salir del espacio
            </button>
          </div>
        </div>
      </section>
    </>
  );
}
