import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Zap } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import { useCatalog, useLang, useMe, useT } from "../lib/app";
import { money } from "../lib/i18n";
import {
  breakdown,
  DEADLINES,
  deadlineKey,
  earliestNormal,
  estimate,
  formatDue,
  NORMAL_MIN_HOURS,
  type PriceLine,
  slidesKey,
  TIERS,
  tierOld,
  tierPrice,
  toLocalInput,
} from "../lib/order";
import { alert, confirm, haptic } from "../lib/tg";
import { unlockAudio } from "../lib/sound";
import type {
  Deadline,
  Design,
  Lang,
  OrderDraft,
  Package,
  Quote,
  SlideTier,
} from "../lib/types";
import { CouponTear } from "../ui/CouponTear";
import { PaidOverlay } from "../ui/PaidOverlay";
import { BackButton, MainButton } from "../ui/TelegramButtons";
import {
  Cell,
  CostTag,
  Group,
  PriceTag,
  Section,
  Segmented,
  Sheet,
  Skeleton,
  TextArea,
  TextInput,
  ToggleCell,
} from "../ui";

const DRAFT_KEY = "sl_draft";

type Draft = Omit<OrderDraft, "slides" | "deadline"> & {
  slides: OrderDraft["slides"] | null;
  deadline: OrderDraft["deadline"] | null;
  key: string; // ключ идемпотентности: повторная отправка не создаст второй заказ
  title_plate?: boolean; // показать поля плашки на титульном
};

function newKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto)
    return crypto.randomUUID();
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
    extra_text: true,
    extra_notes: false,
    need_humor: false,
    title_plate: true,
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
    if (raw)
      return { ...emptyDraft(lang), ...(JSON.parse(raw) as Partial<Draft>) };
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

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));
  const c = catalog.data;
  const first = me.data?.first_order_price ?? null;
  const style = c?.styles.find((s) => s.key === draft.style_key);

  // Чего не хватает на шаге — как в прежней витрине: кнопка подсказывает, поля подсвечиваются
  const missing1 = [
    ...(draft.topic.trim().length < 3 ? (["topic"] as const) : []),
    ...(draft.design === "own" && (draft.template_url ?? "").trim().length <= 3
      ? (["template"] as const)
      : []),
  ];
  const dueOk =
    !!draft.due_at &&
    new Date(draft.due_at).getTime() >= earliestNormal().getTime() - 60_000;
  const missing2 = [
    ...(!draft.slides ? (["slides"] as const) : []),
    ...(!draft.deadline ? (["deadline"] as const) : []),
    ...(draft.deadline === "normal" && !dueOk ? (["due"] as const) : []),
  ];
  const missing =
    step === 1 ? missing1 : step === 2 ? missing2 : [...missing1, ...missing2];
  const [showNeed, setShowNeed] = useState(false);
  const need = (k: (typeof missing)[number]) =>
    showNeed && missing.includes(k as never);
  const step2Ok = missing2.length === 0;

  const quote = useQuery({
    queryKey: [
      "quote",
      draft.slides,
      draft.deadline,
      draft.extra_text,
      draft.extra_notes,
    ],
    queryFn: () =>
      api.quote({
        slides: draft.slides!,
        deadline: draft.deadline!,
        extra_text: draft.extra_text,
        extra_notes: draft.extra_notes,
      }),
    enabled: step2Ok,
    retry: 1,
  });
  // Цена видна сразу, даже пока сервер не ответил (или недоступен); его ответ — точнее, он в приоритете
  const notesFree = !!c?.plans.find((p) => p.code === me.data?.package?.plan)
    ?.notes_free;
  const voucher = me.data?.voucher ?? null; // оплаченная презентация от отменённого заказа
  const local: Quote | null =
    c && draft.slides
      ? estimate(
          c.prices,
          { ...draft, slides: draft.slides },
          first,
          me.data?.package ?? null,
          notesFree,
          voucher,
        )
      : null;
  const shown = (step2Ok && quote.data) || local;
  // Цена без скидки — чтобы зачеркнуть её рядом со скидочной
  const full: number | null =
    c && draft.slides
      ? estimate(
          c.prices,
          { ...draft, slides: draft.slides },
          null,
          null,
          notesFree,
        ).price
      : null;
  // Сколько именно стоит «срочно» для выбранного объёма (пока объём не выбран — для самого маленького)
  const urgentTier: SlideTier =
    draft.slides && draft.slides !== "s30" ? draft.slides : "s10";
  const urgentCalc = (deadline: Deadline) =>
    c
      ? estimate(
          c.prices,
          { ...draft, slides: urgentTier, deadline },
          first,
          me.data?.package ?? null,
          notesFree,
          voucher,
        ).price
      : 0;
  const urgentExtra = urgentCalc("urgent") - urgentCalc("normal");
  const lines: PriceLine[] | null =
    c && draft.slides
      ? breakdown(
          c.prices,
          { ...draft, slides: draft.slides },
          first,
          me.data?.package ?? null,
          notesFree,
          voucher,
        )
      : null;

  const [torn, setTorn] = useState<{ order: number; slides: SlideTier; pay: boolean } | null>(null);
  const [paid, setPaid] = useState<{
    order: number;
    cost: number;
    pkg: Package;
  } | null>(null);
  // звук «оплачено» на iOS играет только после касания — «будим» звук на первом касании формы
  useEffect(() => {
    const once = () => unlockAudio();
    window.addEventListener("pointerdown", once, { once: true });
    return () => window.removeEventListener("pointerdown", once);
  }, []);

  const submit = useMutation({
    mutationFn: (full: boolean) => {
      const { key, title_plate, ...fields } = draft;
      const plate = (v?: string | null) =>
        title_plate ? v?.trim() || null : null;
      const body: OrderDraft = {
        ...fields,
        slides: draft.slides!,
        deadline: draft.deadline!,
        due_at:
          draft.deadline === "normal" && draft.due_at
            ? new Date(draft.due_at).toISOString()
            : null,
        topic: draft.topic.trim(),
        template_url:
          draft.design === "own" ? draft.template_url?.trim() || null : null,
        style_key: draft.design === "ours" ? draft.style_key : null,
        contact: draft.contact?.trim() || null,
        comment: draft.comment?.trim() || null,
        sources: draft.sources?.trim() || null,
        title_author: plate(draft.title_author),
        title_group: plate(draft.title_group),
        title_teacher: plate(draft.title_teacher),
        skip_cover: full,
      };
      return api.createOrder(body, key);
    },
    onSuccess: (order) => {
      localStorage.removeItem(DRAFT_KEY);
      qc.invalidateQueries({ queryKey: ["orders"] });
      const pkg = me.data?.package;
      // Оплачено из пакета — сначала «карта и галочка», потом экран заказа
      if (order.paid_from === "package" && pkg) {
        setPaid({
          order: order.id,
          cost: order.package_cost,
          pkg: { ...pkg, left: Math.max(0, pkg.left - order.package_cost) },
        });
        return;
      }
      // Оплачено купоном (отменённым заказом) — купон рвётся, потом экран заказа
      if (order.by_voucher) {
        qc.invalidateQueries({ queryKey: ["me"] });
        setTorn({ order: order.id, slides: order.slides, pay: !!order.skip_cover && !order.is_paid && order.price > 0 });
        return;
      }
      haptic.success();
      qc.invalidateQueries({ queryKey: ["me"] });
      if (order.skip_cover && !order.is_paid && order.price > 0) {
        nav(`/orders/${order.id}?pay=1`, { replace: true }); // «сразу всю» — сразу к оплате
        return;
      }
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
      // Лимит бесплатных обложек — предлагаем тот же заказ с оплатой сразу (ему лимит не нужен)
      if (e instanceof ApiError && e.code === "cover_limit") {
        void confirm(t("cover_limit")).then((ok) => ok && submit.mutate(true));
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
      document
        .getElementById(`need-${missing[0]}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    setShowNeed(false);
    if (step < 3) {
      setStep(step + 1);
      window.scrollTo({ top: 0 });
    } else go(false);
  };
  // full=true — «Оплатить сразу всю»; основная кнопка всегда бесплатная титулка
  const go = (full: boolean) => {
    if (submit.isPending) return;
    if (full) haptic.tap();
    submit.mutate(full);
  };
  const buttonText = missing.length
    ? t("left", {
        items: missing
          .map((k) => t(`miss_${k}` as Parameters<typeof t>[0]))
          .join(", "),
      })
    : step < 3
      ? t("next")
      : shown?.paid_from === "package"
        ? t("send") // из пакета презентация списывается сразу — «бесплатно» тут было бы неправдой
        : t("send_free_cover");

  return (
    <div className="page no-tabbar">
      {torn && (
        <CouponTear
          slides={torn.slides}
          onDone={() =>
            nav(torn.pay ? `/orders/${torn.order}?pay=1` : `/order/done/${torn.order}`, { replace: true })
          }
        />
      )}
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
        <h1 className="title1">
          {t(step === 1 ? "step1_t" : step === 2 ? "step2_t" : "step3_t")}
        </h1>
        <div className="progress mt-8">
          <i style={{ width: `${(step / 3) * 100}%` }} />
        </div>
      </div>

      {step === 1 && (
        <>
          <Section title={t("f_topic")} id="need-topic" need={need("topic")}>
            <Group>
              <TextArea
                value={draft.topic}
                onChange={(v) => set("topic", v)}
                placeholder={t("f_topic_ph")}
                maxLength={300}
                rows={2}
              />
            </Group>
          </Section>
          {/* Подпись на титульном — сразу после темы: студенту она нужна почти всегда, выключается одним касанием */}
          <Section
            title={t("plate_t")}
            footer={draft.title_plate ? t("plate_hint") : undefined}
          >
            <Group>
              <ToggleCell
                title={t("x_plate")}
                subtitle={t("x_plate_x")}
                on={!!draft.title_plate}
                onChange={(v) => set("title_plate", v)}
              />
              {draft.title_plate && (
                <>
                  <TextInput
                    value={draft.title_author ?? ""}
                    onChange={(v) => set("title_author", v)}
                    label={t("f_author")}
                    placeholder={t("f_author_ph")}
                    maxLength={120}
                  />
                  <TextInput
                    value={draft.title_group ?? ""}
                    onChange={(v) => set("title_group", v)}
                    label={t("f_group")}
                    placeholder={t("f_group_ph")}
                    maxLength={60}
                  />
                  <TextInput
                    value={draft.title_teacher ?? ""}
                    onChange={(v) => set("title_teacher", v)}
                    label={t("f_teacher")}
                    placeholder={t("f_teacher_ph")}
                    maxLength={120}
                  />
                </>
              )}
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
                  <Cell
                    title={t("f_style")}
                    value={style?.name ?? t("f_style_none")}
                    chevron
                    onClick={() => setStylePicker(true)}
                  />
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
                      old={
                        tierOld(c.prices, tier, first)
                          ? money(tierOld(c.prices, tier, first)!)
                          : null
                      }
                      sum={t("sum")}
                    />
                  }
                  checked={draft.slides === tier}
                  onClick={() =>
                    setDraft((d) => ({
                      ...d,
                      slides: tier,
                      deadline:
                        tier === "s30" && d.deadline === "urgent"
                          ? null
                          : d.deadline,
                    }))
                  }
                />
              ))}
            </Group>
          </Section>
          <Section
            title={t("f_deadline")}
            id="need-deadline"
            need={need("deadline")}
          >
            <Group>
              {DEADLINES.map((d) => (
                <Fragment key={d}>
                  <Cell
                    title={t(deadlineKey(d))}
                    subtitle={t(
                      `${deadlineKey(d)}_x` as Parameters<typeof t>[0],
                    )}
                    value={
                      d === "urgent" ? (
                        <CostTag on={draft.deadline === d}>
                          +{money(urgentExtra)} {t("sum")}
                        </CostTag>
                      ) : undefined
                    }
                    checked={draft.deadline === d}
                    disabled={d === "urgent" && draft.slides === "s30"}
                    onClick={() => set("deadline", d)}
                  />
                  {d === "normal" && draft.deadline === "normal" && (
                    <div
                      className={`field-cell due-cell${need("due") ? " need" : ""}`}
                    >
                      <div className="field-label">{t("f_due")}</div>
                      <input
                        className="field"
                        type="datetime-local"
                        min={toLocalInput(earliestNormal())}
                        step={1800}
                        value={
                          draft.due_at
                            ? toLocalInput(new Date(draft.due_at))
                            : ""
                        }
                        onChange={(e) =>
                          set(
                            "due_at",
                            e.target.value
                              ? new Date(e.target.value).toISOString()
                              : null,
                          )
                        }
                      />
                    </div>
                  )}
                </Fragment>
              ))}
            </Group>
          </Section>
          {draft.deadline === "normal" && draft.due_at && !dueOk && (
            <p className="due-warn">
              {t("due_too_soon", { h: NORMAL_MIN_HOURS })}
            </p>
          )}
          {/* Платное — отдельным блоком, с суммой */}
          <Section title={t("f_paid")}>
            <Group>
              <ToggleCell
                title={t("x_notes")}
                subtitle={t("x_notes_x")}
                tag={
                  notesFree && me.data?.package ? (
                    <CostTag free>{t("in_price")}</CostTag>
                  ) : (
                    <CostTag on={draft.extra_notes}>
                      +{money(c.prices.extra_notes)} {t("sum")}
                    </CostTag>
                  )
                }
                on={draft.extra_notes}
                onChange={(v) => set("extra_notes", v)}
              />
            </Group>
          </Section>
          {shown && (
            <PriceCard
              q={shown}
              old={full}
              lines={lines}
              slides={draft.slides}
            />
          )}
        </>
      )}

      {step === 3 && (
        <>
          <Section>
            <Group>
              <Cell title={draft.topic} onClick={() => setStep(1)} chevron />
              <Cell
                title={t("d_slides")}
                value={draft.slides && t(slidesKey(draft.slides))}
                onClick={() => setStep(2)}
              />
              <Cell
                title={t("d_deadline")}
                value={
                  draft.deadline === "normal" && draft.due_at
                    ? formatDue(draft.due_at, lang)
                    : draft.deadline && t(deadlineKey(draft.deadline))
                }
                onClick={() => setStep(2)}
              />
              <Cell
                title={t("d_lang")}
                value={
                  { ru: "Русский", uz: "O‘zbek", en: "English" }[
                    draft.pres_lang
                  ]
                }
                onClick={() => setStep(1)}
              />
              <Cell
                title={t("d_design")}
                value={
                  draft.design === "own"
                    ? t("ds_own")
                    : (style?.name ?? t("ds_ours"))
                }
                onClick={() => setStep(1)}
              />
              {draft.title_plate &&
                (draft.title_author ||
                  draft.title_group ||
                  draft.title_teacher) && (
                  <Cell
                    title={t("x_plate")}
                    subtitle={[
                      draft.title_author,
                      draft.title_group,
                      draft.title_teacher,
                    ]
                      .filter((x) => x?.trim())
                      .join(" · ")}
                    onClick={() => setStep(1)}
                  />
                )}
            </Group>
          </Section>

          <Section title={`${t("more_t")} · ${t("optional")}`}>
            <Group>
              <TextArea
                value={draft.comment ?? ""}
                onChange={(v) => set("comment", v)}
                label={t("f_comment")}
                placeholder={t("f_comment_ph")}
                maxLength={400}
                rows={2}
              />
              <TextArea
                value={draft.sources ?? ""}
                onChange={(v) => set("sources", v)}
                label={t("f_sources")}
                placeholder={t("f_sources_ph")}
                maxLength={1500}
                rows={2}
              />
              <TextInput
                value={draft.contact ?? ""}
                onChange={(v) => set("contact", v)}
                label={t("f_contact")}
                placeholder={t("f_contact_ph")}
                maxLength={60}
                inputMode="tel"
              />
            </Group>
            <div className="mt-8">
              <Group>
                <ToggleCell
                  title={t("f_files")}
                  on={draft.has_source_files}
                  onChange={(v) => set("has_source_files", v)}
                />
              </Group>
            </div>
          </Section>

          {shown ? (
            <PriceCard
              q={shown}
              old={full}
              lines={lines}
              slides={draft.slides}
            />
          ) : (
            <Skeleton height={28} width={140} />
          )}

          {/* Вторая кнопка: не ждать титулку, а оплатить и получить всю презентацию */}
          {shown && shown.paid_from !== "package" && shown.price > 0 && !missing.length && (
            <div className="full-now">
              <button className="full-now-btn" disabled={submit.isPending} onClick={() => go(true)}>
                <Zap size={18} />
                <span>{t("send_pay_now", { price: `${money(shown.price)} ${t("sum")}` })}</span>
              </button>
              <p className="footnote secondary">{t("full_now_x")}</p>
            </div>
          )}
        </>
      )}

      {!paid && !torn && (
        <MainButton
          text={buttonText}
          muted={missing.length > 0}
          loading={submit.isPending}
          onClick={next}
        />
      )}

      <Sheet
        open={stylePicker}
        onClose={() => setStylePicker(false)}
        title={t("f_style")}
      >
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
              icon={
                <img
                  src={s.images[0]}
                  alt=""
                  style={{
                    width: 30,
                    height: 30,
                    objectFit: "cover",
                    borderRadius: 7,
                  }}
                />
              }
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

function PriceCard({
  payNow = false,
  q,
  old,
  lines,
  slides,
}: {
  payNow?: boolean;
  q: Quote;
  old?: number | null;
  lines: PriceLine[] | null;
  slides: SlideTier | null;
}) {
  const t = useT();
  const label = (l: PriceLine) =>
    l.key === "base"
      ? slides
        ? t(slidesKey(slides))
        : t("price_base")
      : l.key === "voucher"
        ? t(l.amount ? "price_voucher_more" : "price_voucher")
      : l.key === "package"
        ? t("price_package", {
            cost: q.package_cost,
            left: q.package_left_after ?? 0,
          })
        : l.key === "urgent"
          ? t("dl_urgent")
          : t("x_notes");
  // строки показываем, только если они сходятся с итогом сервера — иначе одна сумма
  const sum = lines?.reduce((a, l) => a + l.amount, 0);
  const showLines = !!lines && sum === q.price && (lines.length > 1 || (lines[0]?.key === "voucher" && lines[0].amount > 0));
  return (
    <Section title={t("price_t")} footer={payNow ? t("price_pay_now") : t("price_free_now")}>
      <div className="card price-card">
        {showLines &&
          lines!.map((l) => (
            <div
              key={l.key}
              className={`price-line${l.key === "urgent" || l.key === "notes" ? " extra" : ""}`}
            >
              <span>{label(l)}</span>
              <span className="tabular">
                {l.key === "voucher" && !l.amount ? (
                  <span className="secondary">{t("price_voucher_paid")}</span>
                ) : (
                  <>
                    {l.key === "base" || l.key === "package" || l.key === "voucher" ? "" : "+"}
                    {money(l.amount)} {t("sum")}
                  </>
                )}
              </span>
            </div>
          ))}
        {!showLines && q.voucher && (
          <div className="price-line">
            <span>{t("price_voucher")}</span>
          </div>
        )}
        {!showLines && q.paid_from === "package" && (
          <div className="price-line">
            <span>
              {t("price_package", {
                cost: q.package_cost,
                left: q.package_left_after ?? 0,
              })}
            </span>
          </div>
        )}
        <div
          className={`row spread price-total${showLines ? " sep" : ""}`}
          style={{ flexWrap: "wrap", gap: 8 }}
        >
          <span className="subhead secondary">
            {t(q.paid_from === "package" || q.voucher ? "price_extra" : "price_total")}
          </span>
          <span className="title2 tabular">
            <PriceTag
              now={money(q.price)}
              old={
                (q.first_order_discount || q.voucher) && old && old > q.price
                  ? money(old)
                  : null
              }
              sum={t("sum")}
            />
          </span>
        </div>
        {q.first_order_discount && (
          <span className="badge gold mt-8">{t("price_first")}</span>
        )}
      </div>
    </Section>
  );
}
