"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
} from "react";
import {
  DEFAULT_THEME_PREFERENCE,
  isThemePreference,
  THEME_STORAGE_KEY,
  type ResolvedTheme,
  type ThemePreference,
} from "@/lib/theme";
export type { ResolvedTheme, ThemePreference } from "@/lib/theme";

type ThemeContextValue = {
  preference: ThemePreference;
  resolvedTheme: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);
const themeListeners = new Set<() => void>();

function getStoredPreference() {
  if (typeof window === "undefined") return DEFAULT_THEME_PREFERENCE;

  try {
    const storedPreference = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(storedPreference) ? storedPreference : DEFAULT_THEME_PREFERENCE;
  } catch {
    return DEFAULT_THEME_PREFERENCE;
  }
}

function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference === "light" || preference === "dark") return preference;

  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(preference: ThemePreference, resolvedTheme: ResolvedTheme) {
  if (typeof document !== "undefined") {
    document.documentElement.classList.toggle("dark", resolvedTheme === "dark");
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.dataset.themePreference = preference;
  }
}

function getThemeSnapshot() {
  const preference = getStoredPreference();
  return `${preference}:${resolveTheme(preference)}`;
}

function getServerThemeSnapshot() {
  return `${DEFAULT_THEME_PREFERENCE}:dark`;
}

function parseThemeSnapshot(snapshot: string): {
  preference: ThemePreference;
  resolvedTheme: ResolvedTheme;
} {
  const [preference, resolvedTheme] = snapshot.split(":");

  return {
    preference: isThemePreference(preference) ? preference : DEFAULT_THEME_PREFERENCE,
    resolvedTheme: resolvedTheme === "light" ? "light" : "dark",
  };
}

function notifyThemeListeners() {
  themeListeners.forEach((listener) => listener());
}

function subscribeToThemeChanges(listener: () => void) {
  if (typeof window === "undefined") return () => {};

  themeListeners.add(listener);

  const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
  const handleStorageChange = (event: StorageEvent) => {
    if (event.key === THEME_STORAGE_KEY) listener();
  };

  mediaQuery.addEventListener("change", listener);
  window.addEventListener("storage", handleStorageChange);

  return () => {
    themeListeners.delete(listener);
    mediaQuery.removeEventListener("change", listener);
    window.removeEventListener("storage", handleStorageChange);
  };
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const snapshot = useSyncExternalStore(
    subscribeToThemeChanges,
    getThemeSnapshot,
    getServerThemeSnapshot,
  );

  const { preference, resolvedTheme } = useMemo(
    () => parseThemeSnapshot(snapshot),
    [snapshot],
  );

  const setPreference = useCallback((nextPreference: ThemePreference) => {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, nextPreference);
    } catch {
      return;
    }

    applyTheme(nextPreference, resolveTheme(nextPreference));
    notifyThemeListeners();
  }, []);

  useEffect(() => {
    applyTheme(preference, resolvedTheme);
  }, [preference, resolvedTheme]);

  const value = useMemo(
    () => ({ preference, resolvedTheme, setPreference }),
    [preference, resolvedTheme, setPreference],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);

  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider");
  }

  return context;
}
