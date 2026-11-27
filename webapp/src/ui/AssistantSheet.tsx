import { useQuery } from "@tanstack/react-query";
import { BookOpen, ExternalLink, Image as ImageIcon, LineChart, ListTree, Newspaper, Plus, Youtube } from "lucide-react";
import { useState, type ReactNode } from "react";

import { ApiError, researchApi } from "../lib/api";
import { useLang, useT } from "../lib/app";
import type { Key } from "../lib/i18n";
import { haptic, openLink } from "../lib/tg";
import type { DeckAsset, DeckElement, Fact, FoundPhoto, Paper, ResearchPlan, Stats, Video } from "../lib/types";
import { Button, Chips, Sheet, Skeleton } from "../ui";

type Tab = "plan" | "facts" | "papers" | "photos" | "stats" | "videos";
const COUNTRIES = ["UZ", "KZ", "KG", "TJ", "TM", "RU", "US", "CN", "WLD"];
const uid = () => Math.random().toString(36).slice(2, 12);

/** Подпись-источник внизу слайда. */
export function captionEl(text: string): DeckElement {
  return {
    id: uid(),
    type: "text",
    role: "caption",
    box: { x: 0.06, y: 0.9, w: 0.88, h: 0.07 },
    text,
    style: { size: 12, color: "muted" },
  };
}

/** Большие числа — в тысячах / млн / млрд, чтобы график читался. Не больше 8 точек, последняя — всегда. */
export function chartFromStats(s: Stats, units: { k: string; m: string; b: string }): DeckElement {
  const n = s.values.length;
  const step = Math.max(1, Math.ceil(n / 8));
  const idx: number[] = [];
  for (let i = n - 1; i >= 0 && idx.length < 8; i -= step) idx.unshift(i);
  const max = Math.max(...idx.map((i) => Math.abs(s.values[i] ?? 0)));
  const [div, unit] = max >= 1e9 ? [1e9, units.b] : max >= 1e6 ? [1e6, units.m] : max >= 1e4 ? [1e3, units.k] : [1, ""];
  const round = (v: number) => Math.round((v / div) * 10) / 10;
  return {
    id: uid(),
    type: "chart",
    box: { x: 0.08, y: 0.3, w: 0.84, h: 0.55 },
    chart: {
      kind: "bar",
      labels: idx.map((i) => s.labels[i] ?? ""),
      series: [{ name: `${s.label}${unit ? `, ${unit}` : ""}`, values: idx.map((i) => round(s.values[i] ?? 0)) }],
      unit,
    },
    anim: { preset: "grow" },
  };
}

export function AssistantSheet({
  open,
  onClose,
  deckId,
  topic,
  onElements,
  onSlides,
  onPhoto,
}: {
  open: boolean;
  onClose: () => void;
  deckId: number;
  topic: string;
  /** newSlide — положить на новый слайд после текущего (факт, график), иначе — на текущий (ссылка) */
  onElements: (els: DeckElement[], newSlide?: boolean) => void;
  onSlides: (titles: string[]) => void;
  onPhoto: (asset: DeckAsset, caption: string) => void;
}) {
  const t = useT();
  const { lang } = useLang();
  const [tab, setTab] = useState<Tab>("plan");
  const [q, setQ] = useState(topic);
  const [asked, setAsked] = useState<Record<string, string>>({}); // вкладка → запрос, по которому искали
  const sources = useQuery({ queryKey: ["research-sources"], queryFn: researchApi.sources, enabled: open, staleTime: Infinity });
  const [country, setCountry] = useState("UZ");
  const [indicator, setIndicator] = useState("SP.POP.TOTL");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const key = tab === "stats" ? `${country}:${indicator}` : q.trim();
  const run = asked[tab] === key && key.length >= 2;
  const done = () => {
    haptic.success();
    onClose();
  };

  const result = useQuery({
    queryKey: ["research", tab, key, lang],
    enabled: open && run,
    staleTime: 30 * 60_000,
    retry: false,
    queryFn: async (): Promise<unknown> => {
      switch (tab) {
        case "plan":
          return researchApi.plan(key, lang);
        case "facts":
          return researchApi.facts(key, lang);
        case "papers":
          return researchApi.papers(key);
        case "photos":
          return researchApi.photos(key);
        case "stats":
          return researchApi.stats(country, indicator, lang);
        case "videos":
          return researchApi.videos(key, lang);
      }
    },
  });

  const tabs: { value: Tab; label: string; icon: typeof ListTree }[] = [
    { value: "plan", label: t("a_plan"), icon: ListTree },
    { value: "facts", label: t("a_facts"), icon: BookOpen },
    { value: "papers", label: t("a_papers"), icon: Newspaper },
    { value: "photos", label: t("a_photos"), icon: ImageIcon },
    { value: "stats", label: t("a_stats"), icon: LineChart },
  ];
  if (sources.data?.videos) tabs.push({ value: "videos", label: t("a_videos"), icon: Youtube });

  const addPhoto = async (p: FoundPhoto) => {
    setBusy(p.url);
    setError(null);
    try {
      const asset = await researchApi.addPhoto(deckId, p.url);
      onPhoto(asset, `${t("a_photo_by")}: ${p.author || "—"}, ${p.license}, Wikimedia Commons`);
      done();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("b_upload_err"));
    } finally {
      setBusy(null);
    }
  };

  const data = result.data;
  return (
    <Sheet open={open} onClose={onClose} title={t("a_title")}>
      <div className="assist-tabs">
        {tabs.map(({ value, label, icon: Icon }) => (
          <button key={value} className={tab === value ? "on" : ""} onClick={() => (haptic.select(), setTab(value))}>
            <Icon size={18} />
            <span>{label}</span>
          </button>
        ))}
      </div>
      <p className="footnote secondary assist-hint">{t(`a_${tab}_x` as Key)}</p>

      {tab === "stats" ? (
        <>
          <Chips options={COUNTRIES.map((c) => ({ value: c, label: t(`a_c_${c}` as Key) }))} value={country} onChange={setCountry} />
          <div style={{ height: 8 }} />
          <select className="assist-select" value={indicator} onChange={(e) => setIndicator(e.target.value)}>
            {Object.entries(sources.data?.indicators ?? {}).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </>
      ) : (
        <input className="assist-q" value={q} maxLength={200} onChange={(e) => setQ(e.target.value)} placeholder={t("b_new_ph")} />
      )}
      <div style={{ height: 10 }} />
      <Button disabled={key.length < 2 || result.isFetching} onClick={() => setAsked({ ...asked, [tab]: key })}>
        {t("a_find")}
      </Button>

      <div className="assist-results">
        {result.isFetching && <Skeleton height={160} />}
        {(result.error || error) && <p className="assist-error">{error ?? (result.error as Error).message}</p>}
        {run && !result.isFetching && !result.error && (
          <>
            {tab === "plan" && <PlanView plan={data as ResearchPlan | null} onSlides={(s) => (onSlides(s), done())} />}
            {tab === "facts" &&
              (data as Fact[]).map((f) => (
                <Card key={f.url} title={f.title} text={f.text} link={f.url} img={f.image}>
                  <Button
                    small
                    kind="tinted"
                    onClick={() => {
                      onElements([
                        { id: uid(), type: "text", role: "title", box: { x: 0.06, y: 0.08, w: 0.88, h: 0.16 }, text: f.title, style: { size: 36, weight: 700 }, anim: { preset: "fade-up" } },
                        { id: uid(), type: "text", role: "body", box: { x: 0.08, y: 0.3, w: 0.84, h: 0.55 }, text: f.text, style: { size: 22 }, anim: { preset: "fade-up" } },
                        captionEl(`${t("a_source")}: ${t("a_wiki")} — «${f.title}»`),
                      ], true);
                      done();
                    }}
                  >
                    <Plus size={16} /> {t("a_to_slide")}
                  </Button>
                </Card>
              ))}
            {tab === "papers" &&
              (data as Paper[]).map((p) => (
                <Card key={p.url} title={p.title} meta={`${p.authors}${p.year ? ` · ${p.year}` : ""} · ${t("a_cited", { n: p.cited })}`} text={p.abstract} link={p.url}>
                  <Button
                    small
                    kind="tinted"
                    onClick={() => {
                      onElements([captionEl(`${t("a_source")}: ${p.authors}${p.year ? ` (${p.year})` : ""}. ${p.title}`)]);
                      done();
                    }}
                  >
                    <Plus size={16} /> {t("a_cite")}
                  </Button>
                </Card>
              ))}
            {tab === "photos" && (
              <div className="assist-photos">
                {(data as FoundPhoto[]).map((p) => (
                  <button key={p.url} className="assist-photo" disabled={!!busy} onClick={() => void addPhoto(p)}>
                    <img src={p.thumb} alt="" loading="lazy" onError={(e) => (e.currentTarget.style.visibility = "hidden")} />
                    <span>{busy === p.url ? "…" : `${p.author || "—"} · ${p.license}`}</span>
                  </button>
                ))}
              </div>
            )}
            {tab === "stats" && data && (
              <StatsView s={data as Stats} country={t(`a_c_${country}` as Key)} onAdd={(els) => (onElements(els, true), done())} />
            )}
            {tab === "videos" &&
              (data as Video[]).map((v) => (
                <Card key={v.url} title={v.title} meta={`${v.channel}${v.published ? ` · ${v.published}` : ""}`} link={v.url} img={v.thumb}>
                  <Button
                    small
                    kind="tinted"
                    onClick={() => {
                      onElements([captionEl(`▶ ${v.title} — ${v.url}`)]);
                      done();
                    }}
                  >
                    <Plus size={16} /> {t("a_cite")}
                  </Button>
                </Card>
              ))}
            {Array.isArray(data) && data.length === 0 && <p className="secondary">{t("a_nothing")}</p>}
          </>
        )}
      </div>
    </Sheet>
  );
}

function Card({ title, meta, text, link, img, children }: { title: string; meta?: string; text?: string; link: string; img?: string | null; children?: ReactNode }) {
  const t = useT();
  return (
    <div className="assist-card">
      {img && <img src={img} alt="" loading="lazy" />}
      <b>{title}</b>
      {meta && <small className="secondary">{meta}</small>}
      {text && <p>{text}</p>}
      <div className="row assist-card-actions">
        {children}
        <button className="assist-link" onClick={() => openLink(link)}>
          <ExternalLink size={15} /> {t("a_open")}
        </button>
      </div>
    </div>
  );
}

function PlanView({ plan, onSlides }: { plan: ResearchPlan | null; onSlides: (titles: string[]) => void }) {
  const t = useT();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  if (!plan) return <p className="secondary">{t("a_nothing")}</p>;
  const toggle = (s: string) => {
    haptic.select();
    const next = new Set(picked);
    if (next.has(s)) next.delete(s);
    else next.add(s);
    setPicked(next);
  };
  const ordered = [...plan.items.map((i) => i.title), ...plan.history].filter((s, i, a) => picked.has(s) && a.indexOf(s) === i);
  return (
    <>
      <p className="footnote secondary">
        {t("a_plan_from")}{" "}
        <button className="assist-link" onClick={() => openLink(plan.url)}>
          «{plan.source_title}»
        </button>
      </p>
      <div className="assist-plan">
        {plan.items.map((i) => (
          <label key={`${i.level}-${i.title}`} className={`assist-plan-item l${i.level}`}>
            <input type="checkbox" checked={picked.has(i.title)} onChange={() => toggle(i.title)} />
            <span>{i.title}</span>
          </label>
        ))}
      </div>
      {plan.history.length > 0 && (
        <>
          <div className="field-label" style={{ margin: "14px 0 6px" }}>
            {t("a_story")}
          </div>
          <div className="chips">
            {plan.history.map((h) => (
              <button key={h} className={`chip${picked.has(h) ? " on" : ""}`} onClick={() => toggle(h)}>
                {h}
              </button>
            ))}
          </div>
        </>
      )}
      <div style={{ height: 12 }} />
      <Button disabled={!ordered.length} onClick={() => onSlides(ordered)}>
        {t("a_make_slides", { n: ordered.length })}
      </Button>
    </>
  );
}

function StatsView({ s, country, onAdd }: { s: Stats; country: string; onAdd: (els: DeckElement[]) => void }) {
  const t = useT();
  const el = chartFromStats(s, { k: t("a_k"), m: t("a_m"), b: t("a_b") });
  const series = el.chart?.series[0] ?? { name: "", values: [] };
  const labels = el.chart?.labels ?? [];
  const max = Math.max(1, ...series.values);
  return (
    <div className="assist-card">
      <b>
        {country}: {series.name}
      </b>
      <small className="secondary">
        {s.labels[0]}–{s.labels[s.labels.length - 1]} · World Bank
      </small>
      <div className="assist-mini-bars">
        {series.values.map((v, i) => (
          <div key={i}>
            <i style={{ height: `${(v / max) * 100}%` }} />
            <span>{labels[i]}</span>
          </div>
        ))}
      </div>
      <div className="row assist-card-actions">
        <Button
          small
          kind="tinted"
          onClick={() =>
            onAdd([
              { id: uid(), type: "text", role: "title", box: { x: 0.06, y: 0.08, w: 0.88, h: 0.16 }, text: `${country}: ${s.label}`, style: { size: 36, weight: 700 }, anim: { preset: "fade-up" } },
              el,
              captionEl(`${t("a_source")}: World Bank, ${s.labels[0]}–${s.labels[s.labels.length - 1]}`),
            ])
          }
        >
          <Plus size={16} /> {t("a_to_slide")}
        </Button>
        <button className="assist-link" onClick={() => openLink(s.url)}>
          <ExternalLink size={15} /> {t("a_open")}
        </button>
      </div>
    </div>
  );
}
