import { createClient } from "./client";

type AuthHeadersResult = {
  headers: Record<string, string>;
  token: string | null;
  error: string | null;
};

const AUTH_HEADERS_CACHE_TTL_MS = 5_000;

let authHeadersCache: { result: AuthHeadersResult; expiresAt: number } | null = null;
let authHeadersPromise: Promise<AuthHeadersResult> | null = null;

function decodeJwtPayload(token: string): { exp?: number } | null {
  try {
    const [, payload] = token.split(".");
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    return JSON.parse(window.atob(padded));
  } catch {
    return null;
  }
}

function decodeBase64Url(value: string): string | null {
  try {
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const binary = window.atob(padded);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch {
    return null;
  }
}

function readTokenFromStorageValue(raw: string | null): string | null {
  if (!raw) return null;
  try {
    const decoded = raw.startsWith("base64-") ? decodeBase64Url(raw.slice("base64-".length)) : raw;
    if (!decoded) return null;
    const parsed: unknown = JSON.parse(decoded);
    if (!parsed || typeof parsed !== "object") return null;
    const session = parsed as {
      access_token?: unknown;
      currentSession?: { access_token?: unknown };
    };
    const token = session.access_token || session.currentSession?.access_token;
    return typeof token === "string" && isUsableAccessToken(token) ? token : null;
  } catch {
    return null;
  }
}

function isUsableAccessToken(token: string | null | undefined): token is string {
  if (!token) return false;
  const payload = decodeJwtPayload(token);
  if (!payload?.exp) return false;
  return payload.exp > Math.floor(Date.now() / 1000) + 30;
}

function projectRefFromUrl(): string | null {
  try {
    const host = new URL(process.env.NEXT_PUBLIC_SUPABASE_URL || "").hostname;
    return host.split(".")[0] || null;
  } catch {
    return null;
  }
}

function cookieMap(): Map<string, string> {
  const cookies = new Map<string, string>();
  if (typeof document === "undefined") return cookies;
  for (const part of document.cookie.split(";")) {
    const [name, ...valueParts] = part.trim().split("=");
    if (!name) continue;
    try {
      cookies.set(name, decodeURIComponent(valueParts.join("=")));
    } catch {
      cookies.set(name, valueParts.join("="));
    }
  }
  return cookies;
}

function combineCookieChunks(baseKey: string, cookies: Map<string, string>): string | null {
  const whole = cookies.get(baseKey);
  if (whole) return whole;

  const chunks: string[] = [];
  for (let index = 0; ; index += 1) {
    const chunk = cookies.get(`${baseKey}.${index}`);
    if (!chunk) break;
    chunks.push(chunk);
  }

  return chunks.length ? chunks.join("") : null;
}

function readCachedAccessTokenFromCookies(): string | null {
  if (typeof document === "undefined") return null;
  const cookies = cookieMap();
  const preferredKey = projectRefFromUrl();
  const candidateKeys = [
    ...(preferredKey ? [`sb-${preferredKey}-auth-token`] : []),
    ...Array.from(cookies.keys())
      .filter((key) => key.startsWith("sb-") && key.includes("-auth-token"))
      .map((key) => key.replace(/\.\d+$/, "")),
  ];

  for (const key of Array.from(new Set(candidateKeys))) {
    const token = readTokenFromStorageValue(combineCookieChunks(key, cookies));
    if (token) return token;
  }

  return null;
}

function readCachedAccessTokenFromLocalStorage(): string | null {
  if (typeof window === "undefined") return null;

  const preferredKey = projectRefFromUrl();
  const candidateKeys = [
    ...(preferredKey ? [`sb-${preferredKey}-auth-token`] : []),
    ...Array.from({ length: window.localStorage.length }, (_, index) => window.localStorage.key(index) || "")
      .filter((key) => key.startsWith("sb-") && key.endsWith("-auth-token")),
  ];

  for (const key of Array.from(new Set(candidateKeys))) {
    const token = readTokenFromStorageValue(window.localStorage.getItem(key));
    if (token) return token;
  }

  return null;
}

function readCachedAccessToken(): string | null {
  return readCachedAccessTokenFromCookies() || readCachedAccessTokenFromLocalStorage();
}

async function resolveSupabaseAuthHeaders(): Promise<AuthHeadersResult> {
  try {
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token || null;
    if (isUsableAccessToken(token)) {
      return { headers: { Authorization: `Bearer ${token}` }, token, error: null };
    }
  } catch (error) {
    console.warn("[Supabase Auth] getSession failed; trying cached access token.", error);
  }

  const cachedToken = readCachedAccessToken();
  if (cachedToken) {
    return { headers: { Authorization: `Bearer ${cachedToken}` }, token: cachedToken, error: null };
  }

  return {
    headers: {},
    token: null,
    error: "No pude validar la sesion de Supabase. Volve a iniciar sesion o revisa la conexion con Supabase.",
  };
}

export async function getSupabaseAuthHeaders(): Promise<AuthHeadersResult> {
  if (authHeadersCache && Date.now() < authHeadersCache.expiresAt) {
    return authHeadersCache.result;
  }
  if (authHeadersPromise) return authHeadersPromise;

  authHeadersPromise = resolveSupabaseAuthHeaders()
    .then((result) => {
      if (result.token) {
        authHeadersCache = {
          result,
          expiresAt: Date.now() + AUTH_HEADERS_CACHE_TTL_MS,
        };
      }
      return result;
    })
    .finally(() => {
      authHeadersPromise = null;
    });

  return authHeadersPromise;
}
