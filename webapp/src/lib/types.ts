// Повторяет схемы src/slidelab/api/schemas.py

export type Lang = "ru" | "uz" | "en";
export type SlideTier = "s10" | "s20" | "s30";
export type Deadline = "urgent" | "normal" | "relaxed";
export type Design = "ours" | "own";
export type PlanCode = "week" | "month" | "vip";
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
}

export interface OrderDraft {
  topic: string;
  slides: SlideTier;
  deadline: Deadline;
  pres_lang: Lang;
  design: Design;
  style_key?: string | null;
  template_url?: string | null;
  extra_text: boolean;
  extra_notes: boolean;
  need_humor: boolean;
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
  price: number;
  paid_from: PaidFrom;
  package_cost: number;
  revisions_left: number;
  has_cover: boolean;
  has_result: boolean;
  created_at: string;
  events: { status: OrderStatus; at: string }[];
}

export interface Invoice {
  provider: "stars" | "card";
  url: string | null;
  amount: number;
  currency: string;
}
