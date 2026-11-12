import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import { useCatalog, useLang, useMe, useT } from "../lib/app";
import { money } from "../lib/i18n";
import { DEADLINES, deadlineKey, estimate, slidesKey, TIERS, tierOld, tierPrice } from "../lib/order";
import { alert, haptic } from "../lib/tg";
import { unlockAudio } from "../lib/sound";
import type { Design, Lang, OrderDraft, Package, Quote } from "../lib/types";
import { PaidOverlay } from "../ui/PaidOverlay";
import { BackButton, MainButton } from "../ui/TelegramButtons";
import { Cell, Group, PriceTag, Section, Segmented, Sheet, Skeleton, TextArea, TextInput, ToggleCell } from "../ui";

const DRAFT_KEY = "sl_draft";

type Draft = Omit<OrderDraft, "slides" | "deadline"> & {
  slides: OrderDraft["slides"] | null;
  deadline: OrderDraft["deadline"] | null;
  key: string; // ключ идемпотентности: повторная отправка не создаст второй заказ
  title_plate?: boolean; // показать поля плашки на титульном
};

function newKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

function emptyDraft(lang: Lang): Draft {
  return {
    topic: "",
    slides: null,
    deadline: null,
    pres_lang: lang,
    design: "ours",
    style_key: null,
    template_url: "",
    extra_text: false,
    extra_notes: false,
    need_humor: false,
    title_plate: false,
    title_author: "",
    title_group: "",
    title_teacher: "",
    contact: "",
    comment: "",
    sources: "",
    has_source_files: false,
    key: newKey(),
  };
}

function loadDraft(lang: Lang): Draft {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (raw) return { ...emptyDraft(lang), ...(JSON.parse(raw) as Partial<Draft>) };
  } catch {
    /* повреждённый черновик — начинаем заново */
  }
  return emptyDraft(lang);
}

export function NewOrder() {
  const t = useT();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { lang } = useLang();
  const [params] = useSearchParams();
  const me = useMe();
  const catalog = useCatalog();
  const [step, setStep] = useState(1);
  const [stylePicker, setStylePicker] = useState(false);
  const [draft, setDraft] = useState<Draft>(() => {
    const d = loadDraft(lang);
    const style = params.get("style");
    const design = params.get("design") as Design | null;
    if (style) return { ...d, design: "ours", style_key: style };
    if (design) return { ...d, design };
    return d;
  });

  useEffect(() => {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    } catch {
      /* без черновика тоже работает */
    }
  }, [draft]);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft((d) => ({ ...d, [k]: v }));
  const c = catalog.data;
  const first = me.data?.first_order_price ?? null;
  const style = c?.styles.find((s) => s.key === draft.style_key);

  // Чего не хватает на шаге — как в прежней витрине: кнопка подсказывает, поля подсвечиваются
  const missing1 = [
    ...(draft.topic.trim().length < 3 ? (["topic"] as const) : []),
    ...(draft.design === "own" && (draft.template_url ?? "").trim().length <= 3 ? (["template"] as const) : []),
  ];
  const missing2 = [...(!draft.slides ? (["slides"] as const) : []), ...(!draft.deadline ? (["deadline"] as const) : [])];
  const missing = step === 1 ? missing1 : step === 2 ? missing2 : [...missing1, ...missing2];
  const [showNeed, setShowNeed] = useState(false);
  const need = (k: (typeof missing)[number]) => showNeed && missing.includes(k as never);
  const step2Ok = missing2.length === 0;

  const quote = useQuery({
    queryKey: ["quote", draft.slides, draft.deadline, draft.extra_text, draft.extra_notes],
    queryFn: () =>
      api.quote({ slides: draft.slides!, deadline: draft.deadline!, extra_text: draft.extra_text, extra_notes: draft.extra_notes }),
    enabled: step2Ok,
    retry: 1,
  });
  // Цена видна сразу, даже пока сервер не ответил (или недоступен); его ответ — точнее, он в приоритете
  const notesFree = !!c?.plans.find((p) => p.code === me.data?.package?.plan)?.notes_free;
  const local: Quote | null =
    c && draft.slides ? estimate(c.prices, { ...draft, slides: draft.slides }, first, me.data?.package ?? null, notesFree) : null;
  const shown = (step2Ok && quote.data) || local;
  // Цена без скидки — чтобы зачеркнуть её рядом со скидочной
  const full: number | null =
    c && draft.slides ? estimate(c.prices, { ...draft, slides: draft.slides }, null, null, notesFree).price : null;

  const [paid, setPaid] = useState<{ order: number; cost: number; pkg: Package } | null>(null);
  // звук «оплачено» на iOS играет только после касания — «будим» звук на первом касании формы
  useEffect(() => {
    const once = () => unlockAudio();
    window.addEventListener("pointerdown", once, { once: true });
    return () => window.removeEventListener("pointerdown", once);
  }, []);

  const submit = useMutation({
    mutationFn: () => {
      const { key, title_plate, ...fields } = draft;
      const plate = (v?: string | null) => (title_plate ? v?.trim() || null : null);
      const body: OrderDraft = {
        ...fields,
        slides: draft.slides!,
        deadline: draft.deadline!,
        topic: draft.topic.trim(),
        template_url: draft.design === "own" ? draft.template_url?.trim() || null : null,
        style_key: draft.design === "ours" ? draft.style_key : null,
        contact: draft.contact?.trim() || null,
        comment: draft.comment?.trim() || null,
        sources: draft.sources?.trim() || null,
        title_author: plate(draft.title_author),
        title_group: plate(draft.title_group),
        title_teacher: plate(draft.title_teacher),
      };
      return api.createOrder(body, key);
    },
    onSuccess: (order) => {
      localStorage.removeItem(DRAFT_KEY);
      qc.invalidateQueries({ queryKey: ["orders"] });
      const pkg = me.data?.package;
      // Оплачено из пакета — сначала «карта и галочка», потом экран заказа
      if (order.paid_from === "package" && pkg) {
        setPaid({ order: order.id, cost: order.package_cost, pkg: { ...pkg, left: Math.max(0, pkg.left - order.package_cost) } });
        return;
      }
      haptic.success();
      qc.invalidateQueries({ queryKey: ["me"] });
      nav(`/order/done/${order.id}`, { replace: true });
    },
    onError: (e) => {
      haptic.error();
      // 422 — неполная заявка: возвращаем к шагу, где не хватает данных, а не показываем техническую ошибку
      if (e instanceof ApiError && e.status === 422) {
        setStep(missing1.length ? 1 : missing2.length ? 2 : 3);
        setShowNeed(true);
        void alert(t("error"));
        return;
      }
      void alert(e instanceof ApiError ? e.message : t("error"));
    },
  });

  const back = () => (step > 1 ? setStep(step - 1) : nav(-1));
  const next = () => {
    if (missing.length) {
      haptic.error();
      setShowNeed(true);
      if (step === 3) setStep(missing1.length ? 1 : 2);
      document.getElementById(`need-${missing[0]}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    setShowNeed(false);
    if (step < 3) {
      setStep(step + 1);
      window.scrollTo({ top: 0 });
    } else submit.mutate();
  };
  const buttonText = missing.length
    ? t("left", { items: missing.map((k) => t(`miss_${k}` as Parameters<typeof t>[0])).join(", ") })
    : step < 3
      ? t("next")
      : t("send");

  return (
    <div className="page no-tabbar">
      {paid && (
        <PaidOverlay
          pkg={paid.pkg}
          holder={me.data?.first_name || "SlideLab"}
          cost={paid.cost}
          onDone={() => {
            qc.invalidateQueries({ queryKey: ["me"] });
            nav(`/order/done/${paid.order}`, { replace: true });
          }}
          onBuy={() => {
            qc.invalidateQueries({ queryKey: ["me"] });
            nav("/packages", { replace: true });
          }}
        />
      )}
      <BackButton onClick={back} />
      <div style={{ margin: "8px 0 20px" }}>
        <div className="footnote secondary">{t("step", { n: step })}</div>
        <h1 className="title1">{t(step === 1 ? "step1_t" : step === 2 ? "step2_t" : "step3_t")}</h1>
        <div className="progress mt-8">
          <i style={{ width: `${(step / 3) * 100}%` }} />
        </div>
      </div>

      {step === 1 && (
        <>
          <Section title={t("f_topic")} id="need-topic" need={need("topic")}>
            <Group>
              <TextArea value={draft.topic} onChange={(v) => set("topic", v)} placeholder={t("f_topic_ph")} maxLength={300} rows={2} />
            </Group>
          </Section>
          <Section title={t("f_plang")}>
            <Segmented
              value={draft.pres_lang}
              onChange={(v) => set("pres_lang", v)}
              options={[
                { value: "ru", label: "Русский" },
                { value: "uz", label: "O‘zbek" },
                { value: "en", label: "English" },
              ]}
            />
          </Section>
          <Section
            title={t("f_design")}
            footer={draft.design === "own" ? t("f_template_hint") : undefined}
            id="need-template"
            need={need("template")}
          >
            <Segmented
              value={draft.design}
              onChange={(v) => set("design", v)}
              options={[
                { value: "ours", label: t("ds_ours") },
                { value: "own", label: t("ds_own") },
              ]}
            />
            <div className="mt-8">
              <Group>
                {draft.design === "ours" ? (
                  <Cell title={t("f_style")} value={style?.name ?? t("f_style_none")} chevron onClick={() => setStylePicker(true)} />
                ) : (
                  <TextInput
                    value={draft.template_url ?? ""}
                    onChange={(v) => set("template_url", v)}
                    placeholder={t("f_template_ph")}
                    label={t("f_template")}
                    maxLength={500}
                    inputMode="url"
                  />
                )}
              </Group>
            </div>
          </Section>
        </>
      )}

      {step === 2 && c && (
        <>
          <Section title={t("f_slides")} id="need-slides" need={need("slides")}>
            <Group>
              {TIERS.map((tier) => (
                <Cell
                  key={tier}
                  title={t(slidesKey(tier))}
                  value={
                    <PriceTag
                      now={money(tierPrice(c.prices, tier, first))}
                      old={tierOld(c.prices, tier, first) ? money(tierOld(c.prices, tier, first)!) : null}
                      sum={t("sum")}
                    />
                  }
                  checked={draft.slides === tier}
                  onClick={() =>
                    setDraft((d) => ({ ...d, slides: tier, deadline: tier === "s30" && d.deadline === "urgent" ? null : d.deadline }))
                  }
                />
              ))}
            </Group>
          </Section>
          <Section title={t("f_deadline")} id="need-deadline" need={need("deadline")}>
            <Group>
              {DEADLINES.map((d) => (
                <Cell
                  key={d}
                  title={t(deadlineKey(d))}
                  subtitle={t(`${deadlineKey(d)}_x` as Parameters<typeof t>[0], { pct: c.prices.urgent_pct })}
                  checked={draft.deadline === d}
                  disabled={d === "urgent" && draft.slides === "s30"}
                  onClick={() => set("deadline", d)}
                />
              ))}
            </Group>
          </Section>
          <Section title={t("f_extras")}>
            <Group>
              <ToggleCell
                title={t("x_text")}
                subtitle={`+${money(c.prices.extra_text)} ${t("sum")}`}
                on={draft.extra_text}
                onChange={(v) => set("extra_text", v)}
              />
              <ToggleCell
                title={t("x_notes")}
                subtitle={`+${money(c.prices.extra_notes)} ${t("sum")}`}
                on={draft.extra_notes}
                onChange={(v) => set("extra_notes", v)}
              />
              <ToggleCell
                title={t("x_humor")}
                subtitle={t("x_humor_x")}
                on={draft.need_humor}
                onChange={(v) => set("need_humor", v)}
              />
              <ToggleCell title={t("x_plate")} subtitle={t("x_plate_x")} on={!!draft.title_plate} onChange={(v) => set("title_plate", v)} />
              {draft.title_plate && (
                <>
                  <TextInput value={draft.title_author ?? ""} onChange={(v) => set("title_author", v)} label={t("f_author")} placeholder={t("f_author_ph")} maxLength={120} />
                  <TextInput value={draft.title_group ?? ""} onChange={(v) => set("title_group", v)} label={t("f_group")} placeholder={t("f_group_ph")} maxLength={60} />
                  <TextInput value={draft.title_teacher ?? ""} onChange={(v) => set("title_teacher", v)} label={t("f_teacher")} placeholder={t("f_teacher_ph")} maxLength={120} />
                </>
              )}
            </Group>
          </Section>
          {shown && <PriceCard q={shown} old={full} />}
        </>
      )}

      {step === 3 && (
        <>
          <Section>
            <Group>
              <Cell title={draft.topic} onClick={() => setStep(1)} chevron />
              <Cell title={t("d_slides")} value={draft.slides && t(slidesKey(draft.slides))} onClick={() => setStep(2)} />
              <Cell title={t("d_deadline")} value={draft.deadline && t(deadlineKey(draft.deadline))} onClick={() => setStep(2)} />
              <Cell title={t("d_lang")} value={{ ru: "Русский", uz: "O‘zbek", en: "English" }[draft.pres_lang]} onClick={() => setStep(1)} />
              <Cell
                title={t("d_design")}
                value={draft.design === "own" ? t("ds_own") : style?.name ?? t("ds_ours")}
                onClick={() => setStep(1)}
              />
              {draft.title_plate && (draft.title_author || draft.title_group || draft.title_teacher) && (
                <Cell
                  title={t("x_plate")}
                  subtitle={[draft.title_author, draft.title_group, draft.title_teacher].filter((x) => x?.trim()).join(" · ")}
                  onClick={() => setStep(2)}
                />
              )}
            </Group>
          </Section>

          <Section title={`${t("more_t")} · ${t("optional")}`}>
            <Group>
              <TextArea value={draft.comment ?? ""} onChange={(v) => set("comment", v)} label={t("f_comment")} placeholder={t("f_comment_ph")} maxLength={400} rows={2} />
              <TextArea value={draft.sources ?? ""} onChange={(v) => set("sources", v)} label={t("f_sources")} placeholder={t("f_sources_ph")} maxLength={1500} rows={2} />
              <TextInput value={draft.contact ?? ""} onChange={(v) => set("contact", v)} label={t("f_contact")} placeholder={t("f_contact_ph")} maxLength={60} inputMode="tel" />
            </Group>
            <div className="mt-8">
              <Group>
                <ToggleCell title={t("f_files")} on={draft.has_source_files} onChange={(v) => set("has_source_files", v)} />
              </Group>
            </div>
          </Section>

          {shown ? <PriceCard q={shown} old={full} /> : <Skeleton height={28} width={140} />}
        </>
      )}

      {!paid && <MainButton text={buttonText} muted={missing.length > 0} loading={submit.isPending} onClick={next} />}

      <Sheet open={stylePicker} onClose={() => setStylePicker(false)} title={t("f_style")}>
        <Group>
          <Cell
            title={t("f_style_none")}
            checked={!draft.style_key}
            onClick={() => {
              set("style_key", null);
              setStylePicker(false);
            }}
          />
          {c?.styles.map((s) => (
            <Cell
              key={s.key}
              icon={<img src={s.images[0]} alt="" style={{ width: 30, height: 30, objectFit: "cover", borderRadius: 7 }} />}
              iconBg="transparent"
              title={s.name}
              subtitle={s.hint}
              checked={draft.style_key === s.key}
              onClick={() => {
                set("style_key", s.key);
                setStylePicker(false);
              }}
            />
          ))}
        </Group>
      </Sheet>
    </div>
  );
}

function PriceCard({ q, old }: { q: Quote; old?: number | null }) {
  const t = useT();
  return (
    <Section title={t("price_t")} footer={t("price_free_now")}>
      <div className="card">
        {q.paid_from === "package" ? (
          <>
            <div className="headline">{t("price_package", { cost: q.package_cost, left: q.package_left_after ?? 0 })}</div>
            {q.price > 0 && (
              <div className="subhead secondary mt-8">
                {t("price_extra")}: {money(q.price)} {t("sum")}
              </div>
            )}
          </>
        ) : (
          <div className="row spread" style={{ flexWrap: "wrap", gap: 8 }}>
            <span className="title2 tabular">
              <PriceTag now={money(q.price)} old={q.first_order_discount && old && old > q.price ? money(old) : null} sum={t("sum")} />
            </span>
            {q.first_order_discount && <span className="badge gold">{t("price_first")}</span>}
          </div>
        )}
      </div>
    </Section>
  );
}
