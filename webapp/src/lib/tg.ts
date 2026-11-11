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
  downloadFile?(params: { url: string; file_name: string }, cb?: (accepted: boolean) => void): void;
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

/**
 * Открыто кнопкой «Открыть» (главное приложение в BotFather): страница на GitHub перешла сюда по временной ссылке.
 * После такого перехода Telegram не показывает свои кнопки (MainButton, «Назад»), поэтому рисуем их на странице.
 */
export const redirected: boolean = (() => {
  try {
    if (new URLSearchParams(location.search).has("sl_via")) {
      sessionStorage.setItem("sl_via", "1");
      return true;
    }
    return sessionStorage.getItem("sl_via") === "1";
  } catch {
    return new URLSearchParams(location.search).has("sl_via");
  }
})();
/** Свои кнопки Telegram работают: открыто напрямую из Telegram, без перехода. */
export const nativeButtons = !!tg && !redirected;
if (tg && redirected) {
  try {
    document.documentElement.classList.add("sl-via");
  } catch {
    /* без класса — просто без отступа под «Назад» */
  }
}
export const initData = tg?.initData ?? "";

export const haptic = {
  tap: () => tg?.HapticFeedback.impactOccurred("light"),
  select: () => tg?.HapticFeedback.selectionChanged(),
  success: () => tg?.HapticFeedback.notificationOccurred("success"),
  error: () => tg?.HapticFeedback.notificationOccurred("error"),
};

export function alert(message: string): Promise<void> {
  // Telegram роняет showAlert на пустом или слишком длинном тексте — подстрахуемся
  const text = (message || "").trim().slice(0, 250) || "Что-то пошло не так. Попробуйте ещё раз.";
  return new Promise((resolve) => {
    if (tg) {
      try {
        tg.showAlert(text, resolve);
        return;
      } catch {
        /* попап уже открыт или версия клиента старая — покажем обычным окном */
      }
    }
    window.alert(text);
    resolve();
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
  // Свайп вниз не закрывает и не сворачивает приложение — закрыть можно только крестиком (Telegram 7.7+)
  if (webApp.isVersionAtLeast("7.7")) safe(() => webApp.disableVerticalSwipes?.());
  // Запасной вариант для iOS и старых версий: страница всегда прокручиваемая и никогда не стоит в самом верху,
  // поэтому жест вниз прокручивает страницу, а не утаскивает окно приложения.
  safe(() => {
    const root = document.documentElement;
    root.style.minHeight = "calc(100% + 2px)";
    const nudge = () => {
      if (window.scrollY <= 0) window.scrollTo(0, 1);
    };
    window.addEventListener("touchstart", nudge, { passive: true });
    window.addEventListener("scroll", () => {
      if (window.scrollY <= 0) requestAnimationFrame(nudge);
    }, { passive: true });
    setTimeout(nudge, 300);
  });
  // Высота видимой области от Telegram — для экранов на всю высоту на любых устройствах
  const setVh = () => {
    const h = (webApp as unknown as { viewportStableHeight?: number }).viewportStableHeight;
    if (h) document.documentElement.style.setProperty("--app-h", `${h}px`);
  };
  safe(setVh);
  safe(() => webApp.onEvent("viewportChanged", setVh));
  safe(() => webApp.onEvent("themeChanged", applyTheme));
}
