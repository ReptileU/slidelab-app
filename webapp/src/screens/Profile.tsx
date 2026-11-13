import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleHelp, FileText, Globe, Megaphone, MessageCircle, Package, Palette, Star, SunMoon } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import { useCatalog, useLang, useMe, useOrders, useT } from "../lib/app";
import { alert, confirm, getThemeMode, haptic, hasTelegramColors, openTelegramUrl, setThemeMode, type ThemeMode } from "../lib/tg";
import type { Lang } from "../lib/types";
import { Button, Cell, Group, Section, Sheet, TextArea, Toast } from "../ui";
import { PackCard } from "../ui/PackCard";

const LANGS: Record<Lang, string> = { ru: "Русский", uz: "O‘zbekcha", en: "English" };

export function Profile() {
  const t = useT();
  const nav = useNavigate();
  const { lang, setLang } = useLang();
  const me = useMe();
  const catalog = useCatalog();
  const [sheet, setSheet] = useState<"lang" | "theme" | "ask" | "review" | null>(null);
  const [theme, setTheme] = useState<ThemeMode>(getThemeMode);
  const themes: ThemeMode[] = hasTelegramColors() ? ["telegram", "auto", "light", "dark"] : ["auto", "light", "dark"];
  const [toast, setToast] = useState<string | null>(null);
  const user = me.data;
  const orders = useOrders();
  const ordersN = orders.data?.length ?? 0;
  const pkg = user?.package;

  return (
    <div className="page">
      <div className="prof-hero">
        <div className="center" style={{ margin: "16px 0 22px" }}>
          {user?.photo_url ? (
            <img className="avatar" src={user.photo_url} alt="" />
          ) : (
            <div className="avatar">{(user?.first_name ?? "S").slice(0, 1)}</div>
          )}
          <h1 className="title2 mt-16">{user?.first_name}</h1>
          {user?.username && <div className="subhead secondary">@{user.username}</div>}
        </div>
        <div className="prof-stats">
          <div>
            <b className="tabular">{ordersN}</b>
            <span>{t("prof_orders_n")}</span>
          </div>
          <div>
            <b className="tabular">{pkg ? pkg.left : "—"}</b>
            <span>{pkg ? t("prof_left") : t("prof_nopack")}</span>
          </div>
        </div>
      </div>

      {pkg ? (
        <Section title={t("pkg_my")} action={{ label: t("pkg_all"), onClick: () => nav("/packages") }}>
          <PackCard pkg={pkg} holder={user?.first_name || "SlideLab"} hint={false} />
          {pkg.left <= 1 && (
            <div style={{ marginTop: 18 }}>
              <Button kind="tinted" onClick={() => nav("/packages")}>
                {t("prof_renew")}
              </Button>
            </div>
          )}
        </Section>
      ) : (
        <Section>
          <button className="prof-teaser" onClick={() => nav("/packages")}>
            <Package size={30} />
            <div>
              <div className="headline">{t("prof_teaser_t")}</div>
              <div className="footnote secondary">{t("prof_teaser_s")}</div>
            </div>
            <span className="prof-teaser-go">{t("prof_teaser_go")} ›</span>
          </button>
        </Section>
      )}

      <Section>
        <Group icons>
          <Cell icon={<FileText />} title={t("orders_t")} chevron onClick={() => nav("/orders")} />
          <Cell icon={<Palette />} title={t("styles_t")} chevron onClick={() => nav("/styles")} />
        </Group>
      </Section>

      <Section>
        <Group icons>
          <Cell icon={<Globe />} title={t("lang_t")} value={LANGS[lang]} chevron onClick={() => setSheet("lang")} />
          <Cell icon={<SunMoon />} title={t("theme_t")} value={t(`theme_${theme}`)} chevron onClick={() => setSheet("theme")} />
        </Group>
      </Section>

      <Section>
        <Group icons>
          <Cell icon={<CircleHelp />} title={t("help_t")} chevron onClick={() => nav("/help")} />
          <Cell icon={<MessageCircle />} title={t("ask_t")} chevron onClick={() => setSheet("ask")} />
          <Cell icon={<Star />} title={t("review_t")} chevron onClick={() => setSheet("review")} />
          <Cell
            icon={<Megaphone />}
            title={t("channel_t")}
            value={`@${catalog.data?.channel_username ?? "slidelab_uz"}`}
            onClick={() => openTelegramUrl(`https://t.me/${catalog.data?.channel_username ?? "slidelab_uz"}`)}
          />
        </Group>
      </Section>

      <Sheet open={sheet === "lang"} onClose={() => setSheet(null)} title={t("lang_t")}>
        <Group>
          {(Object.keys(LANGS) as Lang[]).map((l) => (
            <Cell
              key={l}
              title={LANGS[l]}
              checked={l === lang}
              onClick={() => {
                setLang(l);
                setSheet(null);
              }}
            />
          ))}
        </Group>
      </Sheet>

      <Sheet open={sheet === "theme"} onClose={() => setSheet(null)} title={t("theme_t")}>
        <Group>
          {themes.map((m) => (
            <Cell
              key={m}
              title={t(`theme_${m}`)}
              checked={m === theme}
              onClick={() => {
                haptic.select();
                setThemeMode(m);
                setTheme(m);
                setSheet(null);
              }}
            />
          ))}
        </Group>
      </Sheet>

      <AskSheet open={sheet === "ask"} onClose={() => setSheet(null)} onSent={() => setToast(t("ask_sent"))} />
      <ReviewSheet
        open={sheet === "review"}
        onClose={() => setSheet(null)}
        onSent={() => setToast(t("rv_sent"))}
        onWithdrawn={() => setToast(t("rv_withdrawn"))}
      />
      <Toast text={toast} onDone={() => setToast(null)} />
    </div>
  );
}

export function AskSheet({ open, onClose, onSent }: { open: boolean; onClose: () => void; onSent: () => void }) {
  const t = useT();
  const [text, setText] = useState("");
  const send = useMutation({
    mutationFn: () => api.ask(text.trim()),
    onSuccess: () => {
      haptic.success();
      setText("");
      onClose();
      onSent();
    },
    onError: (e) => alert(e instanceof ApiError ? e.message : t("error")),
  });
  return (
    <Sheet open={open} onClose={onClose} title={t("ask_t")}>
      <Group>
        <TextArea value={text} onChange={setText} placeholder={t("ask_ph")} maxLength={1000} rows={4} autoFocus />
      </Group>
      <div className="mt-16">
        <Button disabled={!text.trim() || send.isPending} onClick={() => send.mutate()}>
          {t("send_short")}
        </Button>
      </div>
    </Sheet>
  );
}

function ReviewSheet({
  open,
  onClose,
  onSent,
  onWithdrawn,
}: {
  open: boolean;
  onClose: () => void;
  onSent: () => void;
  onWithdrawn: () => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const [stars, setStars] = useState(5);
  const [text, setText] = useState("");
  const mine = useQuery({ queryKey: ["review"], queryFn: api.myReview, enabled: open, retry: false });
  const sent = mine.data ?? null;
  const fail = (e: unknown) => alert(e instanceof ApiError ? e.message : t("error"));
  const send = useMutation({
    mutationFn: () => api.review(stars, text.trim()),
    onSuccess: () => {
      haptic.success();
      setText("");
      void qc.invalidateQueries({ queryKey: ["review"] });
      onClose();
      onSent();
    },
    onError: fail,
  });
  const withdraw = useMutation({
    mutationFn: (id: number) => api.withdrawReview(id),
    onSuccess: () => {
      haptic.success();
      qc.setQueryData(["review"], null);
      onClose();
      onWithdrawn();
    },
    onError: fail,
  });

  // Отзыв уже отправлен — показываем его и даём отозвать
  if (sent) {
    return (
      <Sheet open={open} onClose={onClose} title={t("rv_mine")}>
        <div className="row" style={{ justifyContent: "center", gap: 8, marginBottom: 12 }} aria-label={`${sent.stars} / 5`}>
          {[1, 2, 3, 4, 5].map((n) => (
            <Star key={n} size={30} strokeWidth={1.5} color="var(--label)" fill={n <= sent.stars ? "var(--label)" : "none"} />
          ))}
        </div>
        {sent.text && (
          <p className="subhead center" style={{ margin: "0 8px 4px", whiteSpace: "pre-wrap" }}>
            {sent.text}
          </p>
        )}
        <div className="mt-16">
          <Button
            kind="gray"
            disabled={withdraw.isPending}
            onClick={async () => {
              if (await confirm(t("rv_withdraw_q"))) withdraw.mutate(sent.id);
            }}
          >
            <span style={{ color: "var(--danger)" }}>{t("rv_withdraw")}</span>
          </Button>
        </div>
      </Sheet>
    );
  }

  return (
    <Sheet open={open} onClose={onClose} title={t("review_t")}>
      <div className="row" style={{ justifyContent: "center", gap: 8, marginBottom: 16 }}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            aria-label={`${n}`}
            onClick={() => {
              haptic.select();
              setStars(n);
            }}
          >
            <Star size={36} strokeWidth={1.5} color="var(--label)" fill={n <= stars ? "var(--label)" : "none"} />
          </button>
        ))}
      </div>
      <Group>
        <TextArea value={text} onChange={setText} placeholder={t("rv_ph")} maxLength={1000} rows={3} />
      </Group>
      <div className="mt-16">
        <Button disabled={send.isPending || mine.isLoading} onClick={() => send.mutate()}>
          {t("send_short")}
        </Button>
      </div>
    </Sheet>
  );
}
