import { getLocales } from "expo-localization";
import { createInstance } from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";
// Nigerian Pidgin: NEEDS NATIVE-SPEAKER REVIEW before release (see "_review" in pcm.json).
import pcm from "./locales/pcm.json";

export const LANGUAGES = [
  { code: "en", native: "English" },
  { code: "pcm", native: "Pidgin" },
] as const;

export type LanguageCode = (typeof LANGUAGES)[number]["code"];

export const resources = { en, pcm } as const;

export function isSupported(code: string | null | undefined): code is LanguageCode {
  return !!code && LANGUAGES.some((l) => l.code === code);
}

/** Device language if supported (Pidgin phones usually report "en"), else English. */
export function deviceLanguage(): LanguageCode {
  try {
    const code = getLocales()[0]?.languageCode;
    return isSupported(code) ? code : "en";
  } catch {
    return "en";
  }
}

// A dedicated instance (rather than i18next's global default) keeps tests and the app isolated.
const i18n = createInstance();
i18n.use(initReactI18next).init({
  resources: Object.fromEntries(Object.entries(resources).map(([k, v]) => [k, { translation: v }])),
  lng: deviceLanguage(),
  fallbackLng: "en",
  interpolation: { escapeValue: false }, // React already escapes
  returnNull: false,
  initAsync: false,
});

export default i18n;
