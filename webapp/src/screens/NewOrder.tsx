import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import { useCatalog, useLang, useMe, useT } from "../lib/app";
import { money } from "../lib/i18n";
import { DEADLINES, deadlineKey, slidesKey, TIERS, tierPrice } from "../lib/order";
import { alert, haptic } from "../lib/tg";
import type { Design, Lang, OrderDraft } from "../lib/types";
import { BackButton, MainButton } from "../ui/TelegramButtons";
import { Cell, Group, Section, Segmented, Sheet, Skeleton, TextArea, TextInput, ToggleCell } from "../ui";

const DRAFT_KEY = "sl_draft";

type Draft = Omit<OrderDraft, "slides" | "deadline"> & {
  slides: OrderDraft["slides"] | null;
  deadline: OrderDraft["deadline"] | null;
  key: string; // ключ идемпотентности: повторная отправка не создаст второй заказ
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

  const step1Ok = draft.topic.trim().length >= 3 && (draft.design === "ours" || (draft.template_url ?? "").trim().length > 3);
  const step2Ok = !!draft.slides && !!draft.deadline;

  const quote = useQuery({
    queryKey: ["quote", draft.slides, draft.deadline, draft.extra_text, draft.extra_notes],
    queryFn: () =>
      api.quote({ slides: draft.slides!, deadline: draft.deadline!, extra_text: draft.extra_text, extra_notes: draft.extra_notes }),
    enabled: step === 3 && step2Ok,
  });

  const submit = useMutation({
    mutationFn: () => {
      const body: OrderDraft = {
        ...draft,
        slides: draft.slides!,
        deadline: draft.deadline!,
        topic: draft.topic.trim(),
        template_url: draft.design === "own" ? draft.template_url?.trim() || null : null,
        style_key: draft.design === "ours" ? draft.style_key : null,
        contact: draft.contact?.trim() || null,
        comment: draft.comment?.trim() || null,
        sources: draft.sources?.trim() || null,
      };
      return api.createOrder(body, draft.key);
    },
    onSuccess: (order) => {
      haptic.success();
      localStorage.removeItem(DRAFT_KEY);
      qc.invalidateQueries({ queryKey: ["orders"] });
      qc.invalidateQueries({ queryKey: ["me"] });
      nav(`/order/done/${order.id}`, { replace: true });
    },
    onError: (e) => {
      haptic.error();
      alert(e instanceof ApiError ? e.message : t("error"));
    },
  });

  const back = () => (step > 1 ? setStep(step - 1) : nav(-1));
  const next = () => {
    if (step < 3) {
      setStep(step + 1);
      window.scrollTo({ top: 0 });
    } else submit.mutate();
  };

  return (
    <div className="page no-tabbar">
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
          <Section title={t("f_topic")}>
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
          <Section title={t("f_design")} footer={draft.design === "own" ? t("f_template_hint") : undefined}>
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
          <Section title={t("f_slides")}>
            <Group>
              {TIERS.map((tier) => (
                <Cell
                  key={tier}
                  title={t(slidesKey(tier))}
                  value={`${money(tierPrice(c.prices, tier, first))} ${t("sum")}`}
                  checked={draft.slides === tier}
                  onClick={() =>
                    setDraft((d) => ({ ...d, slides: tier, deadline: tier === "s30" && d.deadline === "urgent" ? null : d.deadline }))
                  }
                />
              ))}
            </Group>
          </Section>
          <Section title={t("f_deadline")}>
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
            </Group>
          </Section>
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

          <Section title={t("price_t")} footer={t("price_free_now")}>
            <div className="card">
              {quote.data ? (
                <>
                  {quote.data.paid_from === "package" ? (
                    <>
                      <div className="headline">
                        {t("price_package", { cost: quote.data.package_cost, left: quote.data.package_left_after ?? 0 })}
                      </div>
                      {quote.data.price > 0 && (
                        <div className="subhead secondary mt-8">
                          {t("price_extra")}: {money(quote.data.price)} {t("sum")}
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="row spread">
                      <span className="title2 tabular">
                        {money(quote.data.price)} {t("sum")}
                      </span>
                      {quote.data.first_order_discount && <span className="badge gold">{t("price_first")}</span>}
                    </div>
                  )}
                </>
              ) : (
                <Skeleton height={28} width={140} />
              )}
            </div>
          </Section>
        </>
      )}

      <MainButton
        text={step < 3 ? t("next") : t("send")}
        disabled={(step === 1 && !step1Ok) || (step === 2 && !step2Ok)}
        loading={submit.isPending}
        onClick={next}
      />

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
