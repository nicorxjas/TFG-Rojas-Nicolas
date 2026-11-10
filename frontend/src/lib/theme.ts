export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "nyro-theme-preference";
export const DEFAULT_THEME_PREFERENCE: ThemePreference = "system";

export function isThemePreference(value: string | null): value is ThemePreference {
  return value === "system" || value === "light" || value === "dark";
}

export const themeInitScript = `
(function () {
  try {
    var key = "${THEME_STORAGE_KEY}";
    var preference = window.localStorage.getItem(key) || "${DEFAULT_THEME_PREFERENCE}";
    var isValidPreference = preference === "system" || preference === "light" || preference === "dark";
    if (!isValidPreference) preference = "${DEFAULT_THEME_PREFERENCE}";

    var resolvedTheme = preference === "dark" || (
      preference === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
    ) ? "dark" : "light";

    document.documentElement.classList.toggle("dark", resolvedTheme === "dark");
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.dataset.themePreference = preference;
  } catch (_) {}
})();
`;
