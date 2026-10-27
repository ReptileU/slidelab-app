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
): Quote {
  const round = (x: number) => Math.floor((x * prices.urgent_pct + 50) / 100);
  const cost = d.slides === "s30" ? 2 : 1;
  if (pkg && pkg.left >= cost) {
    let x = d.deadline === "urgent" ? round(prices[d.slides]) : 0;
    if (d.extra_text) x += prices.extra_text;
    if (d.extra_notes && !notesFree) x += prices.extra_notes;
    return { price: x, paid_from: "package", package_cost: cost, package_left_after: pkg.left - cost, first_order_discount: false };
  }
  const first = d.slides === "s10" && !!firstOrderPrice;
  let p = first ? firstOrderPrice! : prices[d.slides];
  if (d.deadline === "urgent") p += round(p);
  if (d.extra_text) p += prices.extra_text;
  if (d.extra_notes) p += prices.extra_notes;
  return { price: p, paid_from: "cash", package_cost: 0, package_left_after: null, first_order_discount: first };
}
