import type { Key } from "./i18n";
import type { Deadline, OrderStatus, Prices, SlideTier } from "./types";

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
