import { initData } from "./tg";
import type { Credits, Deck, DeckAsset, DeckBrief, DeckSlide, DeckVersion, QuickCover, BuyPlan, PointsBoxKey, PointsInfo, PointsResult, Referrals, Catalog, Gift, Invoice, Lang, LuckyInfo, LuckyPrize, Me, Order, OrderDraft, Quote, SlideMark } from "./types";

/** Отправленный отзыв клиента — показываем в профиле, его можно отозвать. */
export interface MyReview {
  id: number;
  order_id: number | null;
  stars: number;
  text: string | null;
  created_at: string;
}

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
  // Сервер не ответил за минуту (облако просыпалось, оборвалась связь) — не крутимся вечно, а даём повторить.
  // Повтор заказа безопасен: тот же Idempotency-Key, второго заказа не будет.
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 60_000);
  let res: Response;
  try {
    res = await fetch(`./api${path}`, { ...init, headers, signal: init.signal ?? ctrl.signal });
  } catch {
    throw new ApiError(0, "network", "Нет ответа от сервера. Проверьте интернет и нажмите ещё раз.");
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    // 422 от FastAPI — список ошибок полей; клиенту понятнее общий текст, чем техническое описание
    const detail = typeof body.detail === "string" ? body.detail : res.statusText || `HTTP ${res.status}`;
    throw new ApiError(res.status, body.code ?? "http", detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const post = <T>(path: string, body?: unknown, headers?: HeadersInit) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body), headers });

const put = <T>(path: string, body: unknown) => request<T>(path, { method: "PUT", body: JSON.stringify(body) });
const patch = <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const del = <T>(path: string) => request<T>(path, { method: "DELETE" });

/** Конструктор презентаций: каждое изменение — с версией, ответ — новая версия. */
export const decksApi = {
  list: () => request<DeckBrief[]>("/decks"),
  create: (title: string) => post<Deck>("/decks", { title }),
  get: (id: number) => request<Deck>(`/decks/${id}`),
  remove: (id: number) => del<void>(`/decks/${id}`),
  rename: (id: number, version: number, title: string) => patch<DeckVersion>(`/decks/${id}`, { version, title }),
  saveSlide: (id: number, version: number, slide: DeckSlide) =>
    put<DeckVersion>(`/decks/${id}/slides/${slide.id}`, { version, slide }),
  insertSlide: (id: number, version: number, slide: DeckSlide, after: string | null) =>
    post<DeckVersion>(`/decks/${id}/slides`, { version, slide, after }),
  deleteSlide: (id: number, version: number, slideId: string) =>
    del<DeckVersion>(`/decks/${id}/slides/${slideId}?version=${version}`),
  reorder: (id: number, version: number, order: string[]) => put<DeckVersion>(`/decks/${id}/order`, { version, order }),
  assets: (id: number) => request<DeckAsset[]>(`/decks/${id}/assets`),
  upload: (id: number, data: string, kind: DeckAsset["kind"] = "image") =>
    post<DeckAsset>(`/decks/${id}/assets`, { data, kind }),
  credits: () => request<Credits>("/credits"),
  /** Адрес картинки с сервера — относительный, от корня API. */
  assetSrc: (url: string) => `.${url}`,
};

export const api = {
  me: () => request<Me>("/me"),
  setLang: (lang: Lang) => request<Me>("/me", { method: "PATCH", body: JSON.stringify({ lang }) }),
  catalog: (lang: Lang) => request<Catalog>(`/catalog?lang=${lang}`),

  quote: (q: Pick<OrderDraft, "slides" | "deadline" | "extra_text" | "extra_notes">) => post<Quote>("/orders/quote", q),
  createOrder: (draft: OrderDraft, key: string) => post<Order>("/orders", draft, { "Idempotency-Key": key }),
  orders: () => request<Order[]>("/orders"),
  order: (id: number) => request<Order>(`/orders/${id}`),
  quickCover: (body: QuickCover, key: string) => post<Order>("/orders/quick-cover", body, { "Idempotency-Key": key }),
  completeOrder: (id: number, draft: OrderDraft) => post<Order>(`/orders/${id}/complete`, draft),
  approveCover: (id: number) => post<Order>(`/orders/${id}/approve-cover`),
  hideOrder: (id: number) => post<{ ok: boolean }>(`/orders/${id}/hide`),
  cancelOrder: (id: number) => post<Order>(`/orders/${id}/cancel`),
  coverFirst: (id: number) => post<Order>(`/orders/${id}/cover-first`),
  redoCover: (id: number, text: string) => post(`/orders/${id}/redo-cover`, { text }),
  orderInvoice: (id: number, provider: "stars" | "card") =>
    post<Invoice>(`/orders/${id}/invoice`, { provider, app: true }),
  orderReceipt: (id: number, image: string) => post(`/orders/${id}/receipt`, { image }),
  revise: (id: number, text: string, marks: SlideMark[] = [], shots: string[] = []) =>
    post<Order>(`/orders/${id}/revisions`, { text, marks, shots }),
  downloads: (id: number) => request<{ name: string; url: string }[]>(`/orders/${id}/downloads`),

  /** PDF готовой презентации — байты для pdf.js. */
  async deckPdf(id: number): Promise<ArrayBuffer> {
    const headers = new Headers();
    if (initData) headers.set("Authorization", `tma ${initData}`);
    const res = await fetch(`./api/orders/${id}/deck.pdf`, { headers });
    if (!res.ok) throw new ApiError(res.status, "deck", res.statusText);
    return res.arrayBuffer();
  },
  sendFiles: (id: number) => post(`/orders/${id}/send-files`),

  packageInvoice: (plan: BuyPlan, provider: "stars" | "card", gift = false) =>
    post<Invoice>(`/packages/${plan}/invoice`, { provider, app: true, gift }),
  packageReceipt: (plan: BuyPlan, image: string, gift = false) => post(`/packages/${plan}/receipt`, { image, gift }),
  lucky: () => request<LuckyInfo>("/packages/lucky"),
  luckyOpen: () => post<LuckyPrize>("/packages/lucky/open"),
  points: () => request<PointsInfo>("/packages/points"),
  referrals: () => request<Referrals>("/me/referrals"),
  openWelcome: () => post<PointsResult>("/me/referrals/welcome"),
  shareInvite: () => post<{ prepared_id: string | null }>("/me/referrals/share"),
  pointsOpen: (key: PointsBoxKey) => post<PointsResult>(`/packages/points/${key}`),
  ask: (text: string) => post("/support/messages", { text }),
  review: (stars: number, text: string, orderId?: number) =>
    post("/reviews", { stars, text: text || null, order_id: orderId ?? null }),
  myReview: () => request<MyReview | null>("/reviews/mine"),
  withdrawReview: (id: number) => request(`/reviews/${id}`, { method: "DELETE" }),

  gifts: () => request<Gift[]>("/gifts"),
  makeGift: (body: { kind: "coupon"; coupon_id: number } | { kind: "pack" }) => post<Gift>("/gifts", body),
  shareGift: (id: number) => post<{ prepared_id: string | null }>(`/gifts/${id}/share`),
  revokeGift: (id: number) => request(`/gifts/${id}`, { method: "DELETE" }),
  setWalletCover: (image: string) => post<Me>("/me/wallet-cover", { image }),
  resetWalletCover: () => request<Me>("/me/wallet-cover", { method: "DELETE" }),
  /** Обложка кошелька — с авторизацией, как и обложка заказа */
  async walletCoverUrl(): Promise<string> {
    const headers = new Headers();
    if (initData) headers.set("Authorization", `tma ${initData}`);
    const res = await fetch("./api/me/wallet-cover", { headers });
    if (!res.ok) throw new ApiError(res.status, "wallet", res.statusText);
    return URL.createObjectURL(await res.blob());
  },

  /** Обложка — с авторизацией, поэтому через fetch и blob, а не <img src>. */
  async coverUrl(id: number): Promise<string> {
    const headers = new Headers();
    if (initData) headers.set("Authorization", `tma ${initData}`);
    const res = await fetch(`./api/orders/${id}/cover`, { headers });
    if (!res.ok) throw new ApiError(res.status, "cover", res.statusText);
    return URL.createObjectURL(await res.blob());
  },

  /** Миниатюра заказа (первый слайд или обложка). Кэш на время сессии — список не мигает при возврате. */
  thumbUrl(id: number): Promise<string> {
    let found = thumbs.get(id);
    if (!found) {
      const headers = new Headers();
      if (initData) headers.set("Authorization", `tma ${initData}`);
      found = fetch(`./api/orders/${id}/thumb`, { headers }).then(async (res) => {
        if (!res.ok) throw new ApiError(res.status, "thumb", res.statusText);
        return URL.createObjectURL(await res.blob());
      });
      found.catch(() => thumbs.delete(id));
      thumbs.set(id, found);
    }
    return found;
  },
};

const thumbs = new Map<number, Promise<string>>();
