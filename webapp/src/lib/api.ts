import { initData } from "./tg";
import type { Catalog, Invoice, Lang, Me, Order, OrderDraft, PlanCode, Quote } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (initData) headers.set("Authorization", `tma ${initData}`);
  if (init.body) headers.set("Content-Type", "application/json");
  const res = await fetch(`./api${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    // 422 от FastAPI — список ошибок полей; клиенту понятнее общий текст, чем техническое описание
    const detail = typeof body.detail === "string" ? body.detail : res.statusText || `HTTP ${res.status}`;
    throw new ApiError(res.status, body.code ?? "http", detail);
  }
  return (await res.json()) as T;
}

const post = <T>(path: string, body?: unknown, headers?: HeadersInit) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body), headers });

export const api = {
  me: () => request<Me>("/me"),
  setLang: (lang: Lang) => request<Me>("/me", { method: "PATCH", body: JSON.stringify({ lang }) }),
  catalog: (lang: Lang) => request<Catalog>(`/catalog?lang=${lang}`),

  quote: (q: Pick<OrderDraft, "slides" | "deadline" | "extra_text" | "extra_notes">) => post<Quote>("/orders/quote", q),
  createOrder: (draft: OrderDraft, key: string) => post<Order>("/orders", draft, { "Idempotency-Key": key }),
  orders: () => request<Order[]>("/orders"),
  order: (id: number) => request<Order>(`/orders/${id}`),
  approveCover: (id: number) => post<Order>(`/orders/${id}/approve-cover`),
  redoCover: (id: number, text: string) => post(`/orders/${id}/redo-cover`, { text }),
  orderInvoice: (id: number, provider: "stars" | "card") => post<Invoice>(`/orders/${id}/invoice`, { provider }),
  revise: (id: number, text: string) => post<Order>(`/orders/${id}/revisions`, { text }),
  sendFiles: (id: number) => post(`/orders/${id}/send-files`),

  packageInvoice: (plan: PlanCode, provider: "stars" | "card") =>
    post<Invoice>(`/packages/${plan}/invoice`, { provider }),
  ask: (text: string) => post("/support/messages", { text }),
  review: (stars: number, text: string, orderId?: number) =>
    post("/reviews", { stars, text: text || null, order_id: orderId ?? null }),

  /** Обложка — с авторизацией, поэтому через fetch и blob, а не <img src>. */
  async coverUrl(id: number): Promise<string> {
    const headers = new Headers();
    if (initData) headers.set("Authorization", `tma ${initData}`);
    const res = await fetch(`./api/orders/${id}/cover`, { headers });
    if (!res.ok) throw new ApiError(res.status, "cover", res.statusText);
    return URL.createObjectURL(await res.blob());
  },
};
