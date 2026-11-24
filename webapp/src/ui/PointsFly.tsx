import { Coins } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";

import { useLang, useMe, useT } from "../lib/app";
import { playTick } from "../lib/sound";
import { haptic } from "../lib/tg";
import { pointsWord } from "../lib/words";

export const DEMO = "sl_points_fly_demo";
const SEEN = "sl_points_seen"; // сколько баллов клиент уже «видел» на вкладке «Пакеты»

function readSeen(): number | null {
  try {
    const v = localStorage.getItem(SEEN);
    return v === null ? null : Number(v);
  } catch {
    return null;
  }
}

function writeSeen(n: number): void {
  try {
    localStorage.setItem(SEEN, String(n));
  } catch {
    /* без памяти браузера — просто покажем анимацию ещё раз */
  }
}

/**
 * Новые баллы после оплаты: монеты вылетают из центра экрана и «залетают» во вкладку «Пакеты»,
 * на вкладке остаётся значок «+50», пока клиент туда не зайдёт. Возвращает этот прирост (для значка).
 */
export function usePointsGain(): { gain: number; flying: number; done: () => void } {
  const me = useMe();
  const { pathname } = useLocation();
  const points = me.data?.points;
  const [flying, setFlying] = useState(0);
  const [gain, setGain] = useState(0);
  const flown = useRef<number | null>(null);

  useEffect(() => {
    // демо (/demo → «Полёт баллов»): показать полёт без настоящей покупки
    let demo = 0;
    try {
      demo = Number(sessionStorage.getItem(DEMO) || 0);
    } catch {
      /* нет памяти — нет демо */
    }
    if (demo > 0 && pathname !== "/packages" && pathname !== "/demo") {
      try {
        sessionStorage.removeItem(DEMO);
      } catch {
        /* ignore */
      }
      setGain(demo);
      setFlying(demo);
      return;
    }
    if (points === undefined) return;
    const seen = readSeen();
    if (pathname === "/packages") {
      // зашёл посмотреть — значок гаснет
      writeSeen(points);
      setGain(0);
      return;
    }
    if (seen === null && points === 0) {
      writeSeen(0);
      return;
    }
    const diff = points - (seen ?? 0);
    if (diff <= 0) {
      if (diff < 0) writeSeen(points); // потратил или сгорели — запоминаем без анимации
      setGain(0);
      return;
    }
    setGain(diff);
    if (flown.current !== points) {
      flown.current = points; // анимация — один раз на каждое новое начисление
      setFlying(diff);
    }
  }, [points, pathname]);

  return { gain, flying, done: () => setFlying(0) };
}

export function PointsFly({ gain, onDone }: { gain: number; onDone: () => void }) {
  const t = useT();
  const { lang } = useLang();
  const layer = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const target = document.querySelector<HTMLElement>('.tabbar a[href$="/packages"]');
    const root = layer.current;
    if (!target || !root) {
      onDone();
      return;
    }
    const to = target.getBoundingClientRect();
    const tx = to.left + to.width / 2;
    const ty = to.top + to.height / 2 - 6;
    const cx = window.innerWidth / 2;
    const cy = window.innerHeight * 0.42;
    const coins = [...root.querySelectorAll<HTMLElement>(".pfly-coin")];
    const timers: number[] = [];
    haptic.success();

    coins.forEach((el, i) => {
      // разлёт веером, потом дугой — в иконку вкладки
      const a = (i / coins.length) * Math.PI * 2;
      const sx = cx + Math.cos(a) * 70;
      const sy = cy + Math.sin(a) * 50;
      const mx = (sx + tx) / 2 + (i % 2 ? 60 : -60);
      const my = Math.min(sy, ty) - 80;
      const delay = 700 + i * 70;
      el.animate(
        [
          { transform: `translate(${cx}px,${cy}px) scale(.2)`, opacity: 0 },
          { transform: `translate(${sx}px,${sy}px) scale(1)`, opacity: 1, offset: 0.25 },
          { transform: `translate(${mx}px,${my}px) scale(.85)`, opacity: 1, offset: 0.62 },
          { transform: `translate(${tx}px,${ty}px) scale(.35)`, opacity: 0.9 },
        ],
        { duration: 1150, delay: delay - 500, easing: "cubic-bezier(.45,0,.3,1)", fill: "both" },
      );
      timers.push(
        window.setTimeout(() => {
          playTick();
          haptic.tap();
          target.classList.remove("tab-catch");
          void target.offsetWidth; // перезапуск анимации «поймал»
          target.classList.add("tab-catch");
        }, delay + 650),
      );
    });
    timers.push(window.setTimeout(onDone, 700 + coins.length * 70 + 900));
    return () => timers.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return createPortal(
    <div className="pfly" ref={layer} aria-live="polite">
      <div className="pfly-chip">
        <Coins size={20} /> +{gain} {pointsWord(lang, gain)}
        <small>{t("pts_fly_to")}</small>
      </div>
      {Array.from({ length: 8 }, (_, i) => (
        <span key={i} className="pfly-coin" />
      ))}
    </div>,
    document.body,
  );
}
