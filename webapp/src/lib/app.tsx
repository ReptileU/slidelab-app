import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api } from "./api";
import { guessLang, translate, type Key } from "./i18n";
import { tg } from "./tg";
import type { Lang, OrderStatus } from "./types";

const STORAGE_KEY = "sl_lang";

function storedLang(): Lang | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "ru" || v === "uz" || v === "en" ? v : null;
  } catch {
    return null;
  }
}

interface LangState {
  lang: Lang;
  chosen: boolean; // выбирал ли клиент язык сам (иначе показываем выбор при первом входе)
  setLang: (l: Lang) => void;
}

const LangContext = createContext<LangState | null>(null);

export function LangProvider({ children }: { children: ReactNode }) {
  const me = useMe();
  const qc = useQueryClient();
  const [local, setLocal] = useState<Lang | null>(storedLang);
  const lang = me.data?.lang ?? local ?? guessLang(tg?.initDataUnsafe.user?.language_code);

  const save = useMutation({
    mutationFn: api.setLang,
    onSuccess: (data) => qc.setQueryData(["me"], data),
  });

  const setLang = useCallback(
    (l: Lang) => {
      setLocal(l);
      try {
        localStorage.setItem(STORAGE_KEY, l);
      } catch {
        /* приватный режим — не страшно */
      }
      save.mutate(l);
    },
    [save],
  );

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const value = useMemo(
    () => ({ lang, chosen: !!(me.data?.lang ?? local), setLang }),
    [lang, me.data?.lang, local, setLang],
  );
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang(): LangState {
  const ctx = useContext(LangContext);
  if (!ctx) throw new Error("LangProvider missing");
  return ctx;
}

export function useT() {
  const { lang } = useLang();
  return useCallback((key: Key, vars?: Record<string, string | number>) => translate(lang, key, vars), [lang]);
}

// --- данные ---

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: api.me, retry: false, staleTime: 30_000 });
}

export function useCatalog() {
  const { lang } = useLang();
  return useQuery({ queryKey: ["catalog", lang], queryFn: () => api.catalog(lang), staleTime: 5 * 60_000 });
}

const LIVE: OrderStatus[] = ["new", "cover", "awaiting_payment", "work", "revision"];

export function useOrders() {
  return useQuery({
    queryKey: ["orders"],
    queryFn: api.orders,
    retry: false,
    refetchInterval: (q) => (q.state.data?.some((o) => LIVE.includes(o.status)) ? 30_000 : false),
  });
}

export function useOrder(id: number) {
  return useQuery({
    queryKey: ["order", id],
    queryFn: () => api.order(id),
    // пока заказ в процессе — обновляем, чтобы обложка и статус появлялись сами
    refetchInterval: (q) => (q.state.data && LIVE.includes(q.state.data.status) ? 15_000 : false),
  });
}
