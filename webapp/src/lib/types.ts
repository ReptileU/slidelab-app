// Повторяет схемы src/slidelab/api/schemas.py

export type Lang = "ru" | "uz" | "en";
export type SlideTier = "s10" | "s20" | "s30";
export type Deadline = "urgent" | "normal" | "relaxed";
export type Design = "ours" | "own";
export type PlanCode = "week" | "month" | "vip";
/** Что можно купить на вкладке «Пакеты»: обычный пакет или бонус-пакет. */
export type BuyPlan = PlanCode | "lucky";
export type BoxPrize = "one" | "two" | "four" | "vip" | "coupons" | "discount" | "points";

export interface LuckyPrize {
  prize: BoxPrize;
  count: number;
}

/** Бонус-пакет: цена, открытые шансы, лимит и купленный, но ещё не открытый пакет. */
export interface LuckyInfo {
  price: number;
  odds: (LuckyPrize & { percent: number })[];
  limit: number;
  window_days: number;
  can_buy: boolean;
  pending: LuckyPrize | null;
}
/** Пакеты за баллы: баллы даются за покупки деньгами (services/points.py). */
export type PointsBoxKey = "small" | "medium" | "large" | "welcome";
export interface PointsBox {
  key: PointsBoxKey;
  price: number;
  prizes: { prize: BoxPrize; value: number; percent: number }[];
}
export interface PointsInfo {
  points: number;
  expire_at: string | null;
  per_presentation: number;
  expire_days: number;
  discount_pct: number | null;
  boxes: PointsBox[];
}
export interface PointsResult {
  prize: BoxPrize;
  value: number;
  points: number;
}
export type PaidFrom = "cash" | "package";
export type OrderStatus = "new" | "cover" | "awaiting_payment" | "work" | "done" | "revision" | "cancelled";

export interface Package {
  plan: PlanCode;
  left: number;
  total: number;
  expires_at: string;
}

export interface Me {
  id: number;
  first_name: string;
  username: string | null;
  photo_url: string | null;
  lang: Lang | null;
  first_order_price: number | null;
  package: Package | null;
  active_orders: number;
  voucher?: SlideTier | null; // оплаченная презентация от отменённого заказа — её объём
  vouchers?: number;
  voucher_list?: SlideTier[]; // объём каждого купона
  coupons?: { id: number; slides: SlideTier; gift?: boolean }[];
  wallet_cover?: string | null; // своя обложка кошелька (версия), null — классическая
  points?: number; // баллы за покупки
  points_expire_at?: string | null;
  discount_pct?: number | null; // карта скидки из пакета за баллы — на следующий заказ
}

export interface Prices {
  s10: number;
  s20: number;
  s30: number;
  urgent_pct: number;
  extra_text: number;
  extra_notes: number;
  first_order_s10: number;
  uzs_per_star: number;
}

export interface Plan {
  code: PlanCode;
  count: number;
  price: number;
  days: number;
  notes_free: boolean;
  priority: boolean;
  max_parallel: number | null;
}

export interface Style {
  key: string;
  name: string;
  hint: string;
  tags: string[];
  images: string[];
  is_real_work: boolean;
}

export interface Work {
  image: string;
  title: string;
  style: string;
}

export interface Catalog {
  prices: Prices;
  plans: Plan[];
  styles: Style[];
  works: Work[];
  faq: { q: string; a: string }[];
  bot_username: string;
  channel_username: string;
  stars: boolean;
}

export interface Quote {
  price: number;
  paid_from: PaidFrom;
  package_cost: number;
  package_left_after: number | null;
  first_order_discount: boolean;
  voucher?: boolean; // база оплачена отменённым заказом
  discount_pct?: number; // применена карта скидки
}

export interface OrderDraft {
  topic: string;
  slides: SlideTier;
  deadline: Deadline;
  due_at?: string | null; // ISO, к какому сроку нужна — только для «Обычно»
  skip_cover?: boolean; // «Сразу всю презентацию» — без бесплатной обложки, оплата сразу
  pres_lang: Lang;
  design: Design;
  style_key?: string | null;
  template_url?: string | null;
  extra_text: boolean;
  extra_notes: boolean;
  need_humor: boolean;
  title_author?: string | null;
  title_group?: string | null;
  title_teacher?: string | null;
  contact?: string | null;
  comment?: string | null;
  sources?: string | null;
  has_source_files: boolean;
}

export interface Order {
  id: number;
  topic: string;
  slides: SlideTier;
  deadline: Deadline;
  pres_lang: Lang;
  design: Design;
  style_key: string | null;
  status: OrderStatus;
  skip_cover?: boolean;
  quick?: boolean; // короткая заявка на бесплатную обложку — объём и срок ещё не выбраны
  title_author?: string | null;
  is_paid?: boolean;
  voucher_open?: boolean;
  cancel_refund?: boolean; // отменить сейчас — оплата вернётся (после начала работы — не всегда) // отменён после оплаты — оплата ждёт следующего заказа
  by_voucher?: boolean; // оплачен отменённым заказом
  price: number;
  paid_from: PaidFrom;
  package_cost: number;
  revisions_left: number;
  has_cover: boolean;
  has_result: boolean;
  has_deck?: boolean;
  created_at: string;
  events: { status: OrderStatus; at: string }[];
}

export interface Invoice {
  provider: "stars" | "card";
  url: string | null;
  amount: number;
  currency: string;
  /** Перевод в приложении: номера карт и получатель. */
  cards: { label: string; number: string }[];
  name: string;
}

/** Правка на слайде: номер слайда, место (доли 0–1) и что поменять. */
export interface SlideMark {
  slide: number;
  x: number;
  y: number;
  text: string;
}

/** Подарок из кошелька: купон или презентации из пакета, ссылкой другу. */
export interface Gift {
  id: number;
  kind: "coupon" | "pack";
  count: number;
  slides: SlideTier | null;
  plan: PlanCode | null;
  link: string;
  created_at: string;
}

/** Пригласить друга (/me/referrals). */
export interface Referrals {
  link: string;
  inviter_points: number;
  friend_points: number;
  paid: number;
  earned: number;
  milestones: { friends: number; prize: "coupon" | "points"; points: number; reached: boolean }[];
  friends: { name: string; joined_at: string; paid_at: string | null; points: number }[];
  invited: boolean;
  welcome: PointsBox | null; // приветственный кейс от друга — пока не открыт
}

/** Короткая заявка «бесплатная обложка»: только тема, стиль, язык и имя на титульном слайде. */
export interface QuickCover {
  topic: string;
  pres_lang: Lang;
  design: Design;
  style_key: string | null;
  template_url: string | null;
  title_author: string | null;
}

// --- Конструктор презентаций (схема — src/slidelab/core/services/decks.py) ---

export type AnimPreset = "none" | "fade" | "fade-up" | "zoom" | "slide-left" | "grow";

export interface DeckBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DeckElement {
  id: string;
  type: "text" | "image" | "chart" | "shape" | "icon" | "flag";
  box: DeckBox;
  role?: "title" | "subtitle" | "body" | "caption" | "number" | "quote";
  text?: string;
  style?: { size?: number; weight?: number; align?: "left" | "center" | "right"; color?: string; italic?: boolean };
  asset_id?: number;
  fit?: "cover" | "contain";
  chart?: {
    kind: "bar" | "line" | "pie" | "donut";
    labels: string[];
    series: { name: string; values: number[] }[];
    unit?: string;
    legend?: boolean;
  };
  shape?: "rect" | "round" | "circle" | "line" | "arrow";
  fill?: string;
  anim?: { preset: AnimPreset; delay?: number; trigger?: "slide" | "click" };
}

export interface DeckSlide {
  id: string;
  layout: string;
  bg?: string;
  bg_asset_id?: number;
  notes?: string;
  elements: DeckElement[];
}

export interface DeckTheme {
  palette: { bg: string; fg: string; accent: string; muted: string };
  fonts: { head: string; body: string };
}

export interface DeckBrief {
  id: number;
  title: string;
  lang: Lang;
  status: "draft" | "exported";
  slides: number;
  updated_at: string;
}

export interface Deck extends DeckBrief {
  version: number;
  body: { v: 1; theme: DeckTheme; slides: DeckSlide[] };
}

export interface DeckVersion {
  id: number;
  version: number;
  updated_at: string;
}

export interface DeckAsset {
  id: number;
  kind: "image" | "logo" | "background";
  width: number;
  height: number;
  bytes: number;
  url: string;
}

export interface Credits {
  balance: number;
  daily_cap: number;
  costs: Record<string, number>;
}
