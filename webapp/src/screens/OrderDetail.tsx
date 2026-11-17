import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Star, Ticket } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import { useLang, useMe, useOrder, useT } from "../lib/app";
import { formatDate, money } from "../lib/i18n";
import { deadlineKey, hintKey, slidesKey, STATUS_BADGE, statusKey, stepState, timelineSteps } from "../lib/order";
import { alert, confirm, haptic } from "../lib/tg";
import type { Order, Package } from "../lib/types";
import { Button, Cell, Group, Img, Section, Sheet, Skeleton, TextArea, Toast } from "../ui";
import { PaySheet } from "../ui/PaySheet";
import { ReturnOverlay } from "../ui/ReturnOverlay";
import { SlideViewer } from "../ui/SlideViewer";
import { BackButton, MainButton } from "../ui/TelegramButtons";

export function OrderDetail() {
  const t = useT();
  const nav = useNavigate();
  const id = Number(useParams().id);
  const query = useOrder(id);
  const order = query.data;

  return (
    <div className="page no-tabbar">
      <BackButton onClick={() => nav("/orders", { replace: true })} />
      {!order ? <Skeleton height={240} /> : <OrderView order={order} />}
      {query.isError && <p className="secondary center">{t("error")}</p>}
    </div>
  );
}

// Клиент может сам отменить заказ, пока презентацию не сдали
const CANCELLABLE = new Set(["new", "cover", "awaiting_payment", "work"]);

function OrderView({ order }: { order: Order }) {
  const t = useT();
  const nav = useNavigate();
  const { lang } = useLang();
  const qc = useQueryClient();
  const [cover, setCover] = useState<string | null>(null);
  // «Сразу всю презентацию»: после заказа приходим сюда с ?pay=1 — окно оплаты открыто сразу
  const [params, setParams] = useSearchParams();
  const payNow = !!order.skip_cover && order.status === "new" && !order.is_paid && order.price > 0;
  const [sheet, setSheet] = useState<"pay" | "redo" | "revise" | null>(payNow && params.get("pay") === "1" ? "pay" : null);
  useEffect(() => {
    if (params.get("pay")) setParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [text, setText] = useState("");
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!order.has_cover) return;
    let url: string | null = null;
    api.coverUrl(order.id).then((u) => setCover((url = u)), () => setCover(null));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [order.id, order.has_cover]);

  const refresh = (data?: Order) => {
    if (data) qc.setQueryData(["order", order.id], data);
    qc.invalidateQueries({ queryKey: ["order", order.id] });
    qc.invalidateQueries({ queryKey: ["orders"] });
    qc.invalidateQueries({ queryKey: ["me"] });
  };
  const fail = (e: unknown) => {
    haptic.error();
    alert(e instanceof ApiError ? e.message : t("error"));
  };

  const approve = useMutation({
    mutationFn: () => api.approveCover(order.id),
    onSuccess: (o) => {
      refresh(o);
      if (o.status === "awaiting_payment") setSheet("pay");
      else setToast(t("hint_work"));
    },
    onError: fail,
  });
  const redo = useMutation({
    mutationFn: () => api.redoCover(order.id, text.trim()),
    onSuccess: () => close(t("redo_sent")),
    onError: fail,
  });
  const revise = useMutation({
    mutationFn: () => api.revise(order.id, text.trim()),
    onSuccess: (o) => {
      refresh(o);
      close(t("revise_sent"));
    },
    onError: fail,
  });
  // «Оплатить сразу всю» нажали случайно — до оплаты возвращаемся к бесплатной титулке
  const coverFirst = useMutation({
    mutationFn: () => api.coverFirst(order.id),
    onSuccess: (o) => {
      setSheet(null);
      refresh(o);
      haptic.success();
      setToast(t("cover_first_ok"));
    },
    onError: fail,
  });
  // Отмена: не оплачен — заказ удаляется; из пакета — презентация возвращается в пакет;
  // оплачен деньгами — оплата переходит на следующий заказ
  const paidCash = !!order.is_paid && order.paid_from === "cash" && order.price > 0 && !order.by_voucher;
  const meQ = useMe();
  const fromPack = order.paid_from === "package";
  // срок пакета вышел — презентация вернётся не в пакет, а купоном
  const packAlive = !!meQ.data?.package;
  const unpaid = !order.is_paid && !order.by_voucher && !fromPack;
  const [back, setBack] = useState<{ pkg: Package | null; coupon: boolean } | null>(null);
  const cancel = useMutation({
    mutationFn: async () => {
      const o = await api.cancelOrder(order.id);
      // свежий пакет — чтобы показать, сколько в нём стало после возврата
      const me = await api.me().catch(() => null);
      return { o, me };
    },
    onSuccess: ({ o, me }) => {
      qc.invalidateQueries({ queryKey: ["orders"] });
      if (me) qc.setQueryData(["me"], me);
      else qc.invalidateQueries({ queryKey: ["me"] });
      if (unpaid) {
        haptic.success();
        nav("/orders", { replace: true });
        return;
      }
      refresh(o);
      // оплата вернулась: в пакет — карта (разбитая собирается), иначе — купон
      const pkg = o.voucher_open ? null : (me?.package ?? null);
      if (o.voucher_open || pkg) setBack({ pkg, coupon: !!o.voucher_open });
      else setToast(t("cancel_ok_pack"));
    },
    onError: fail,
  });
  const askCancel = async () => {
    const q = unpaid ? "cancel_q_unpaid" : fromPack && packAlive ? "cancel_q_pack" : fromPack ? "cancel_q_paid" : paidCash || order.by_voucher ? "cancel_q_paid" : "cancel_q_unpaid";
    if (await confirm(t(q))) cancel.mutate();
  };
  const files = useMutation({
    mutationFn: () => api.sendFiles(order.id),
    onSuccess: () => setToast(t("files_sent")),
    onError: fail,
  });

  function close(message: string) {
    haptic.success();
    setSheet(null);
    setText("");
    setToast(message);
  }

  const steps = timelineSteps(order.status, order.events.map((e) => e.status));
  // последний переход в этот статус (findLast есть не во всех webview Telegram)
  const at = (s: string) => [...order.events].reverse().find((e) => e.status === s)?.at;
  const price = `${money(order.price)} ${t("sum")}`;

  const main = (() => {
    if (payNow) return { text: t("pay_full_btn", { price }), run: () => setSheet("pay"), loading: false };
    switch (order.status) {
      case "cover":
        return { text: order.price > 0 ? t("cover_like_pay", { price }) : t("cover_like"), run: () => approve.mutate(), loading: approve.isPending };
      case "awaiting_payment":
        return { text: t("cover_like_pay", { price }), run: () => setSheet("pay"), loading: false };
      case "done":
        return { text: t("files_get"), run: () => files.mutate(), loading: files.isPending };
      default:
        return null;
    }
  })();

  return (
    <>
      <div style={{ margin: "8px 0 20px" }}>
        <div className="row spread">
          <span className="footnote secondary">{t("order_n", { id: order.id })}</span>
          <span className={`badge ${STATUS_BADGE[order.status]}`}>{t(statusKey(order.status))}</span>
        </div>
        <h1 className="title2 mt-8">{order.topic}</h1>
        <p className="subhead secondary" style={{ margin: "6px 0 0" }}>
          {payNow ? t("hint_full_pay") : order.skip_cover && order.status === "new" ? t("hint_work") : t(hintKey(order.status))}
        </p>
      </div>

      {order.voucher_open && (
        <Section>
          <div className="voucher-note">
            <Ticket size={22} />
            <div className="grow">
              <div className="headline">{t("voucher_kept_t")}</div>
              <div className="footnote secondary">{t("voucher_kept_s")}</div>
            </div>
          </div>
          <div className="mt-12">
            <Button kind="tinted" onClick={() => nav("/order")}>
              {t("voucher_use")}
            </Button>
          </div>
        </Section>
      )}

      {order.has_deck && (
        <Section title={t("v_title")}>
          <SlideViewer
            order={order}
            onSent={(o) => {
              refresh(o);
              close(t("revise_sent"));
            }}
          />
        </Section>
      )}

      {order.has_cover && !order.has_deck && (
        <Section title={t("cover_t")}>
          {cover ? <Img src={cover} alt="" className="cover-img" loading="eager" /> : <Skeleton height={190} />}
          {order.status === "cover" && (
            <div className="mt-8">
              <Button kind="plain" onClick={() => setSheet("redo")}>
                {t("cover_redo")}
              </Button>
            </div>
          )}
        </Section>
      )}

      {order.status === "done" && (
        <Section footer={t("revise_left", { n: order.revisions_left })}>
          <Group>
            <Cell title={t("revise")} chevron onClick={() => setSheet("revise")} />
          </Group>
          <Rating orderId={order.id} />
        </Section>
      )}

      {order.status !== "cancelled" && (
        <Section title={t("tl_t")}>
          <div className="card">
            <div className="timeline">
              {steps.map((s) => {
                const state = stepState(s, order.status);
                const when = at(s);
                return (
                  <div key={s} className={`tl-step ${state}`}>
                    <span className="tl-dot">{state === "done" && <Check strokeWidth={3} />}</span>
                    <div className="grow">
                      <div className="tl-label subhead" style={{ fontWeight: state === "now" ? 600 : 400 }}>
                        {t(statusKey(s))}
                      </div>
                      {when && state !== "todo" && <div className="caption secondary">{formatDate(when, lang)}</div>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </Section>
      )}

      <Section title={t("details_t")}>
        <Group>
          <Cell title={t("d_slides")} value={t(slidesKey(order.slides))} />
          <Cell title={t("d_deadline")} value={t(deadlineKey(order.deadline))} />
          <Cell title={t("d_lang")} value={{ ru: "Русский", uz: "O‘zbek", en: "English" }[order.pres_lang]} />
          <Cell title={t("d_design")} value={order.design === "own" ? t("ds_own") : t("ds_ours")} />
          <Cell
            title={t("d_price")}
            value={
              order.paid_from === "package"
                ? `${t("d_from_package")}${order.price ? ` + ${price}` : ""}`
                : order.by_voucher
                  ? `${t("d_by_voucher")}${order.price ? ` + ${price}` : ""}`
                  : price
            }
          />
        </Group>
      </Section>

      {payNow && (
        <button className="cover-first" disabled={coverFirst.isPending} onClick={() => coverFirst.mutate()}>
          {t("cover_first")}
        </button>
      )}

      {CANCELLABLE.has(order.status) && (
        <button className="order-cancel" disabled={cancel.isPending} onClick={askCancel}>
          {t(unpaid ? "cancel_delete" : "cancel_order")}
        </button>
      )}

      {main && <MainButton text={main.text} loading={main.loading} onClick={main.run} />}

      <PaySheet
        open={sheet === "pay"}
        title={t("pay_t")}
        amount={order.price}
        onClose={() => setSheet(null)}
        createInvoice={(p) => api.orderInvoice(order.id, p)}
        sendReceipt={(image) => api.orderReceipt(order.id, image)}
        onPaid={() => {
          setToast(t("pay_ok"));
          setTimeout(() => refresh(), 1500);
        }}
        onReceipt={() => setToast(t("pay_shot_sent"))}
        extra={
          payNow ? (
            <button className="cover-first" disabled={coverFirst.isPending} onClick={() => coverFirst.mutate()}>
              {t("cover_first")}
            </button>
          ) : null
        }
      />

      <Sheet open={sheet === "redo" || sheet === "revise"} onClose={() => setSheet(null)} title={sheet === "redo" ? t("redo_t") : t("revise_t")}>
        <Group>
          <TextArea
            value={text}
            onChange={setText}
            placeholder={sheet === "redo" ? t("redo_ph") : t("revise_ph")}
            maxLength={1500}
            rows={4}
            autoFocus
          />
        </Group>
        {sheet === "revise" && <p className="footnote secondary" style={{ padding: "8px 16px 0" }}>{t("revise_hint")}</p>}
        <div className="mt-16">
          <Button
            disabled={!text.trim() || redo.isPending || revise.isPending}
            onClick={() => (sheet === "redo" ? redo.mutate() : revise.mutate())}
          >
            {t("send_short")}
          </Button>
        </div>
      </Sheet>

      {back && (
        <ReturnOverlay
          pkg={back.pkg}
          holder={meQ.data?.first_name || "SlideLab"}
          cost={order.package_cost}
          slides={order.slides}
          onDone={() => setBack(null)}
        />
      )}
      <Toast text={toast} onDone={() => setToast(null)} />
    </>
  );
}

function Rating({ orderId }: { orderId: number }) {
  const t = useT();
  const key = `sl_rated_${orderId}`;
  const [stars, setStars] = useState<number>(() => Number(localStorage.getItem(key) ?? 0));
  const send = useMutation({ mutationFn: (n: number) => api.review(n, "", orderId) });

  return (
    <div className="card mt-16 center">
      <div className="subhead secondary">{stars ? t("rv_sent") : t("rate_t")}</div>
      <div className="row" style={{ justifyContent: "center", gap: 6, marginTop: 8 }}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            aria-label={`${n}`}
            disabled={!!stars}
            onClick={() => {
              haptic.success();
              setStars(n);
              localStorage.setItem(key, String(n));
              send.mutate(n);
            }}
          >
            <Star size={32} strokeWidth={1.5} color="var(--label)" fill={n <= stars ? "var(--label)" : "none"} />
          </button>
        ))}
      </div>
    </div>
  );
}
