import type { Key } from "./i18n";
import type { Deadline, OrderStatus, Package, Prices, Quote, SlideTier } from "./types";

export const TIERS: SlideTier[] = ["s10", "s20", "s30"];
export const DEADLINES: Deadline[] = ["urgent", "normal", "relaxed"];

export const STATUS_BADGE: Record<OrderStatus, string> = {
  new: "gray",
  cover: "orange",
  awaiting_payment: "orange",
  work: "",
  revision: "",
  done: "green",
  cancelled: "gray",
};

/** Этапы для ленты: «ждём оплату» показываем, только если заказ через него прошёл. */
export function timelineSteps(status: OrderStatus, visited: OrderStatus[]): OrderStatus[] {
  const steps: OrderStatus[] = ["new", "cover"];
  if (status === "awaiting_payment" || visited.includes("awaiting_payment")) steps.push("awaiting_payment");
  steps.push("work", "done");
  return steps;
}

const ORDER_OF: OrderStatus[] = ["new", "cover", "awaiting_payment", "work", "done"];

export function stepState(step: OrderStatus, status: OrderStatus): "done" | "now" | "todo" {
  const current = status === "revision" ? "work" : status;
  const a = ORDER_OF.indexOf(step);
  const b = ORDER_OF.indexOf(current);
  if (status === "done" || a < b) return "done";
  return a === b ? "now" : "todo";
}

/** Старая цена для зачёркивания: есть, только если действует скидка на первую презентацию. */
export function tierOld(prices: Prices, tier: SlideTier, firstOrderPrice: number | null): number | null {
  return tier === "s10" && firstOrderPrice && firstOrderPrice < prices.s10 ? prices.s10 : null;
}

/** Цена объёма для показа на шаге 2; итог всё равно считает сервер. */
export function tierPrice(prices: Prices, tier: SlideTier, firstOrderPrice: number | null): number {
  if (tier === "s10" && firstOrderPrice) return firstOrderPrice;
  return prices[tier];
}

export const statusKey = (s: OrderStatus) => `st_${s}` as Key;
export const hintKey = (s: OrderStatus) => `hint_${s}` as Key;
export const slidesKey = (s: SlideTier) => `slides_${s}` as Key;
export const deadlineKey = (d: Deadline) => `dl_${d}` as Key;

/** Цена сразу на телефоне — как в прежней витрине, без ожидания сервера. Сервер потом считает то же самое. */
export function estimate(
  prices: Prices,
  d: { slides: SlideTier; deadline: Deadline | null; extra_text: boolean; extra_notes: boolean },
  firstOrderPrice: number | null,
  pkg: Package | null,
  notesFree: boolean,
  voucher: SlideTier | null = null,
): Quote {
  const round = (x: number) => Math.floor((x * prices.urgent_pct + 50) / 100);
  const cost = d.slides === "s30" ? 2 : 1;
  if (voucher) {
    // презентация уже оплачена отменённым заказом: больше слайдов — только разница, плюс доплаты
    let x = Math.max(0, prices[d.slides] - prices[voucher]);
    if (d.deadline === "urgent") x += round(prices[d.slides]);
    if (d.extra_notes) x += prices.extra_notes;
    return { price: x, paid_from: "cash", package_cost: 0, package_left_after: null, first_order_discount: false, voucher: true };
  }
  if (pkg && pkg.left >= cost) {
    // текст входит в цену — доплачиваются только срочность и речь (у VIP речь бесплатно)
    let x = d.deadline === "urgent" ? round(prices[d.slides]) : 0;
    if (d.extra_notes && !notesFree) x += prices.extra_notes;
    return { price: x, paid_from: "package", package_cost: cost, package_left_after: pkg.left - cost, first_order_discount: false };
  }
  const first = d.slides === "s10" && !!firstOrderPrice;
  let p = first ? firstOrderPrice! : prices[d.slides];
  if (d.deadline === "urgent") p += round(p);
  if (d.extra_notes) p += prices.extra_notes;
  return { price: p, paid_from: "cash", package_cost: 0, package_left_after: null, first_order_discount: first };
}

/** Из чего складывается цена — строки для карточки «Стоимость». Сумма строк равна estimate().price. */
export interface PriceLine {
  key: "base" | "package" | "voucher" | "urgent" | "notes";
  amount: number;
}
export function breakdown(
  prices: Prices,
  d: { slides: SlideTier; deadline: Deadline | null; extra_text: boolean; extra_notes: boolean },
  firstOrderPrice: number | null,
  pkg: Package | null,
  notesFree: boolean,
  voucher: SlideTier | null = null,
): PriceLine[] {
  const round = (x: number) => Math.floor((x * prices.urgent_pct + 50) / 100);
  const cost = d.slides === "s30" ? 2 : 1;
  if (voucher) {
    const lines: PriceLine[] = [{ key: "voucher", amount: Math.max(0, prices[d.slides] - prices[voucher]) }];
    if (d.deadline === "urgent") lines.push({ key: "urgent", amount: round(prices[d.slides]) });
    if (d.extra_notes) lines.push({ key: "notes", amount: prices.extra_notes });
    return lines;
  }
  const fromPkg = !!pkg && pkg.left >= cost;
  const base = fromPkg ? 0 : d.slides === "s10" && firstOrderPrice ? firstOrderPrice : prices[d.slides];
  const lines: PriceLine[] = [{ key: fromPkg ? "package" : "base", amount: base }];
  if (d.deadline === "urgent") lines.push({ key: "urgent", amount: round(fromPkg ? prices[d.slides] : base) });
  if (d.extra_notes && !(fromPkg && notesFree)) lines.push({ key: "notes", amount: prices.extra_notes });
  return lines;
}

/** «Обычно» — не раньше чем через столько часов (как NORMAL_MIN_HOURS на сервере); быстрее — «Срочно». */
export const NORMAL_MIN_HOURS = 48;

/** Значение для <input type="datetime-local"> в местном времени устройства. */
export function toLocalInput(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Самый ранний срок для «Обычно», округлённый вверх до получаса. */
export function earliestNormal(now = new Date()): Date {
  const d = new Date(now.getTime() + NORMAL_MIN_HOURS * 3600_000);
  d.setSeconds(0, 0);
  const m = d.getMinutes();
  if (m % 30) d.setMinutes(m + (30 - (m % 30)));
  return d;
}

/** «20 нояб., 15:00» — срок для кнопки и сводки. */
export function formatDue(iso: string, lang: string): string {
  return new Date(iso).toLocaleString(lang === "en" ? "en-GB" : lang === "uz" ? "uz-UZ" : "ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
