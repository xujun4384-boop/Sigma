import React, { createContext, useContext, useCallback, useMemo } from "react";
import type { Lang } from "./translations";
import { translations } from "./translations";

const STORAGE_KEY = "sigma_language";

interface I18nContextValue {
  lang: Lang;
  t: (key: string, ...args: (string | number)[]) => string;
  setLang: (lang: Lang) => void;
}

const I18nContext = createContext<I18nContextValue>({
  lang: "zh",
  t: (key: string) => key,
  setLang: () => {},
});

export const I18nProvider: React.FC<{ lang: Lang; onChange: (lang: Lang) => void; children: React.ReactNode }> = ({
  lang,
  onChange,
  children,
}) => {
  const t = useCallback(
    (key: string, ...args: (string | number)[]): string => {
      const template = translations[lang]?.[key] ?? translations.en?.[key] ?? key;
      if (args.length === 0) return template;
      return template.replace(/\{(\d+)\}/g, (_, idx) => String(args[Number(idx)] ?? ""));
    },
    [lang],
  );

  const value = useMemo(() => ({ lang, t, setLang: onChange }), [lang, t, onChange]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
};

export function useTranslation() {
  return useContext(I18nContext);
}

export function getSavedLanguage(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "zh") return saved;
  } catch {}
  return "zh";
}

export function saveLanguage(lang: Lang) {
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {}
}
