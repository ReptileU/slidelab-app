// Тонкая обёртка над Telegram.WebApp: все вызовы безопасны вне Telegram (разработка в браузере).

type Haptic = "light" | "medium" | "heavy" | "rigid" | "soft";
type Notify = "success" | "warning" | "error";

interface BottomButton {
  setParams(p: { text?: string; color?: string; text_color?: string; is_active?: boolean; is_visible?: boolean }): void;
  onClick(cb: () => void): void;
  offClick(cb: () => void): void;
  showProgress(leaveActive?: boolean): void;
  hideProgress(): void;
}

interface WebApp {
  initData: string;
  initDataUnsafe: { user?: { first_name?: string; language_code?: string; photo_url?: string } };
  platform: string;
  colorScheme: "light" | "dark";
  themeParams: Record<string, string | undefined>;
  version: string;
  isVersionAtLeast(v: string): boolean;
  ready(): void;
  expand(): void;
  close(): void;
  setHeaderColor(c: string): void;
  setBackgroundColor(c: string): void;
  setBottomBarColor?(c: string): void;
  disableVerticalSwipes?(): void;
  enableClosingConfirmation(): void;
  disableClosingConfirmation(): void;
  onEvent(e: string, cb: (...args: never[]) => void): void;
  offEvent(e: string, cb: (...args: never[]) => void): void;
  openInvoice(url: string, cb?: (status: "paid" | "cancelled" | "failed" | "pending") => void): void;
  openTelegramLink(url: string): void;
  openLink(url: string): void;
  showAlert(message: string, cb?: () => void): void;
  showConfirm(message: string, cb: (ok: boolean) => void): void;
  MainButton: BottomButton;
  BackButton: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
  HapticFeedback: {
    impactOccurred(s: Haptic): void;
    notificationOccurred(t: Notify): void;
    selectionChanged(): void;
  };
}

declare global {
  interface Window {
    Telegram?: { WebApp?: WebApp };
  }
}

const webApp = window.Telegram?.WebApp;

/** Открыто внутри Telegram (а не в обычном браузере при разработке). */
export const inTelegram = !!webApp && !!webApp.initData;
/** Внутри Telegram, но без данных пользователя: так бывает, если открыть кнопкой у клавиатуры. */
export const inTelegramWithoutUser = !!webApp && !webApp.initData && webApp.platform !== "unknown";

export function closeApp(): void {
  try {
    webApp?.close();
  } catch {
    /* вне Telegram закрывать нечего */
  }
}
export const tg: WebApp | undefined = inTelegram ? webApp : undefined;
export const initData = tg?.initData ?? "";

export const haptic = {
  tap: () => tg?.HapticFeedback.impactOccurred("light"),
  select: () => tg?.HapticFeedback.selectionChanged(),
  success: () => tg?.HapticFeedback.notificationOccurred("success"),
  error: () => tg?.HapticFeedback.notificationOccurred("error"),
};

export function alert(message: string): Promise<void> {
  return new Promise((resolve) => {
    if (tg) tg.showAlert(message, resolve);
    else {
      window.alert(message);
      resolve();
    }
  });
}

export function confirm(message: string): Promise<boolean> {
  return new Promise((resolve) => {
    if (tg) tg.showConfirm(message, resolve);
    else resolve(window.confirm(message));
  });
}

export function openInvoice(url: string): Promise<"paid" | "cancelled" | "failed" | "pending"> {
  return new Promise((resolve) => {
    if (tg) tg.openInvoice(url, resolve);
    else {
      window.open(url, "_blank");
      resolve("pending");
    }
  });
}

export function openChat(botUsername: string): void {
  const url = `https://t.me/${botUsername}`;
  if (tg) tg.openTelegramLink(url);
  else window.open(url, "_blank");
}

export function openTelegramUrl(url: string): void {
  if (tg) tg.openTelegramLink(url);
  else window.open(url, "_blank");
}

/** Палитра своя, монохромная; от Telegram берём только светлую или тёмную схему. */
/** Вызов метода Telegram, которого может не быть в старой версии клиента: ошибка не должна ронять приложение. */
function safe(call: () => void): void {
  try {
    call();
  } catch (e) {
    console.warn("[SlideLab] Telegram API:", e);
  }
}

export function applyTheme(): void {
  const root = document.documentElement;
  const dark = tg ? tg.colorScheme === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "dark" : "light";
  if (!tg) return;
  const webApp = tg;
  const bg = getComputedStyle(root).getPropertyValue("--bg").trim();
  // Произвольный цвет шапки — с Telegram 6.9; раньше только ключи темы
  if (bg && webApp.isVersionAtLeast("6.9")) {
    safe(() => webApp.setHeaderColor(bg));
    safe(() => webApp.setBackgroundColor(bg));
  } else {
    safe(() => webApp.setHeaderColor("secondary_bg_color"));
  }
  if (bg && webApp.isVersionAtLeast("7.10")) safe(() => webApp.setBottomBarColor?.(bg));
}

export function initTelegram(): void {
  safe(applyTheme);
  if (!tg) return;
  const webApp = tg;
  safe(() => webApp.ready());
  safe(() => webApp.expand());
  safe(() => webApp.onEvent("themeChanged", applyTheme));
}
