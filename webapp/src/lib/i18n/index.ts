import type { Lang } from "../types";

import * as form from "./form";
import * as order from "./order";
import * as rewards from "./rewards";
import * as wallet from "./wallet";
import * as common from "./common";

// Тексты разложены по разделам приложения (form, order, rewards, wallet, common) — правка одного раздела не трогает остальные.
const ru = {
  ...form.ru,
  ...order.ru,
  ...rewards.ru,
  ...wallet.ru,
  ...common.ru,
} as const;

export type Key = keyof typeof ru;
type Dict = Record<Key, string>;

const uz: Dict = {
  ...form.uz,
  ...order.uz,
  ...rewards.uz,
  ...wallet.uz,
  ...common.uz,
};
const en: Dict = {
  ...form.en,
  ...order.en,
  ...rewards.en,
  ...wallet.en,
  ...common.en,
};

export const DICTS: Record<Lang, Dict> = { ru, uz, en };

export function translate(
  lang: Lang,
  key: Key,
  vars?: Record<string, string | number>,
): string {
  let text = DICTS[lang][key] ?? ru[key];
  if (vars)
    for (const [k, v] of Object.entries(vars))
      text = text.replace(`{${k}}`, String(v));
  return text;
}

export function guessLang(code?: string): Lang {
  if (code === "uz") return "uz";
  if (code && !["ru", "uk", "be", "kk"].some((p) => code.startsWith(p)))
    return "en";
  return "ru";
}

/** 29000 → «29 000» */
export function money(n: number): string {
  return n.toLocaleString("ru-RU").replace(/\s/g, " ");
}

export function formatDate(iso: string, lang: Lang): string {
  const locale =
    lang === "en" ? "en-GB" : lang === "uz" ? "uz-Latn-UZ" : "ru-RU";
  return new Date(iso).toLocaleDateString(locale, {
    day: "numeric",
    month: "long",
  });
}
