import { api } from "./api";

let strings: Record<string, string> = {};
let locale = "ru";

export function getLocale(): string {
  return locale;
}

export async function loadLocale(code: string): Promise<void> {
  locale = code === "en" ? "en" : "ru";
  strings = await api.locale(locale);
}

export function t(key: string, vars: Record<string, string | number> = {}): string {
  let text = strings[key] ?? key;
  for (const [name, value] of Object.entries(vars)) {
    text = text.replaceAll(`{${name}}`, String(value));
  }
  return text;
}
