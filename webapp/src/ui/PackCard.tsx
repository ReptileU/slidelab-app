import { useEffect, useRef, useState } from "react";

import { useLang, useT } from "../lib/app";
import { formatDate } from "../lib/i18n";
import { haptic, tg } from "../lib/tg";
import type { Package } from "../lib/types";

/** Датчики Telegram (Bot API 8.0+): наклон телефона и тряска. Без них — только наклон пальцем или мышью. */
interface Sensor {
  isStarted?: boolean;
  start(params: { refresh_rate?: number; need_absolute?: boolean }, cb?: (ok: boolean) => void): void;
  stop(cb?: (ok: boolean) => void): void;
}
type Sensors = {
  DeviceOrientation?: Sensor & { alpha: number | null; beta: number | null; gamma: number | null };
  Accelerometer?: Sensor & { x: number | null; y: number | null; z: number | null };
};

const TIER: Record<string, { name: string; cls: string }> = {
  week: { name: "SILVER", cls: "silver" },
  month: { name: "PLATINUM", cls: "platinum" },
  vip: { name: "GOLD · VIP", cls: "gold" },
};
const ART: Record<string, string> = { week: "p0", month: "p1b", vip: "p2" };

const clamp = (v: number, a = -1, b = 1) => Math.max(a, Math.min(b, v));

/**
 * Виртуальная «пластиковая» карта пакета: остаток презентаций крупно, точки — сколько осталось.
 * Ничего не нажимается: карта наклоняется за пальцем и за наклоном телефона, а от тряски по ней пробегает блик.
 */
export function PackCard({ pkg, holder, hint = true }: { pkg: Package; holder: string; hint?: boolean }) {
  const t = useT();
  const { lang } = useLang();
  const card = useRef<HTMLDivElement>(null);
  const target = useRef({ x: 0, y: 0 });
  const current = useRef({ x: 0, y: 0 });
  const touching = useRef(false);
  const [shake, setShake] = useState(0);
  const tier = TIER[pkg.plan] ?? { name: "SILVER", cls: "silver" };

  // Плавное следование за целью — без рывков от датчиков
  useEffect(() => {
    let raf = 0;
    const loop = () => {
      const c = current.current;
      const g = target.current;
      c.x += (g.x - c.x) * 0.12;
      c.y += (g.y - c.y) * 0.12;
      const el = card.current;
      if (el) {
        el.style.setProperty("--rx", `${(-c.y * 12).toFixed(2)}deg`);
        el.style.setProperty("--ry", `${(c.x * 14).toFixed(2)}deg`);
        el.style.setProperty("--gx", `${(50 + c.x * 45).toFixed(1)}%`);
        el.style.setProperty("--gy", `${(50 + c.y * 45).toFixed(1)}%`);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  // Наклон телефона и тряска
  useEffect(() => {
    const s = tg as unknown as Sensors | undefined;
    const cleanups: (() => void)[] = [];
    let base: { b: number; g: number } | null = null;
    let lastShake = 0;

    const tilt = (beta: number, gamma: number) => {
      if (touching.current) return;
      if (!base) base = { b: beta, g: gamma };
      target.current = { x: clamp((gamma - base.g) / 0.5), y: clamp((beta - base.b) / 0.5) };
    };
    const kick = (mag: number) => {
      const now = Date.now();
      if (mag < 14 || now - lastShake < 1200) return;
      lastShake = now;
      haptic.success();
      setShake((n) => n + 1);
    };

    const canSensors = !!tg && tg.isVersionAtLeast("8.0");
    if (canSensors && s?.DeviceOrientation) {
      const o = s.DeviceOrientation;
      const onO = () => o.beta != null && o.gamma != null && tilt(o.beta, o.gamma);
      try {
        tg!.onEvent("deviceOrientationChanged", onO);
        o.start({ refresh_rate: 40 });
        cleanups.push(() => {
          tg!.offEvent("deviceOrientationChanged", onO);
          o.stop();
        });
      } catch {
        /* датчика нет — наклон только пальцем */
      }
    } else {
      // Вне Telegram (или старая версия) — датчик браузера, где он доступен без разрешения
      const onW = (e: DeviceOrientationEvent) => {
        if (e.beta == null || e.gamma == null) return;
        tilt((e.beta * Math.PI) / 180, (e.gamma * Math.PI) / 180);
      };
      window.addEventListener("deviceorientation", onW);
      cleanups.push(() => window.removeEventListener("deviceorientation", onW));
    }
    if (canSensors && s?.Accelerometer) {
      const a = s.Accelerometer;
      const onA = () => {
        if (a.x == null || a.y == null || a.z == null) return;
        kick(Math.abs(Math.hypot(a.x, a.y, a.z) - 9.8));
      };
      try {
        tg!.onEvent("accelerometerChanged", onA);
        a.start({ refresh_rate: 60 });
        cleanups.push(() => {
          tg!.offEvent("accelerometerChanged", onA);
          a.stop();
        });
      } catch {
        /* без акселерометра — без эффекта тряски */
      }
    } else {
      const onM = (e: DeviceMotionEvent) => {
        const g = e.accelerationIncludingGravity;
        if (g?.x == null || g.y == null || g.z == null) return;
        kick(Math.abs(Math.hypot(g.x, g.y, g.z) - 9.8));
      };
      window.addEventListener("devicemotion", onM);
      cleanups.push(() => window.removeEventListener("devicemotion", onM));
    }
    return () => cleanups.forEach((f) => f());
  }, []);

  function follow(e: React.PointerEvent<HTMLDivElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    touching.current = true;
    target.current = {
      x: clamp(((e.clientX - box.left) / box.width) * 2 - 1),
      y: clamp(((e.clientY - box.top) / box.height) * 2 - 1),
    };
  }
  function release() {
    touching.current = false;
    target.current = { x: 0, y: 0 };
  }

  const dots = Array.from({ length: pkg.total }, (_, i) => i < pkg.left);
  const date = formatDate(pkg.expires_at, lang);

  return (
    <div className="pcard-stage">
      <div
        ref={card}
        className={`pcard ${tier.cls}${shake ? " shaken" : ""}`}
        key={shake}
        onPointerMove={follow}
        onPointerDown={follow}
        onPointerLeave={release}
        onPointerUp={release}
        onPointerCancel={release}
        role="img"
        aria-label={`${t("pkg_my")}: ${t("pkg_left", { left: pkg.left, total: pkg.total })}`}
      >
        <img className="pcard-art" src={`./packs/${ART[pkg.plan] ?? "p0"}.webp`} alt="" draggable={false} />
        <div className="pcard-holo" />
        <div className="pcard-glare" />
        <div className="pcard-in">
          <div className="pcard-top">
            <span className="pcard-brand">
              <b>S</b>
              <i>›</i> SlideLab
            </span>
            <span className="pcard-tier">{tier.name}</span>
          </div>
          <div className="pcard-mid">
            <span className="pcard-chip" aria-hidden />
            <div className="pcard-bal">
              <span className="pcard-num tabular">{pkg.left}</span>
              <span className="pcard-of">
                / {pkg.total}
                <small>{t("pkg_card_left")}</small>
              </span>
            </div>
          </div>
          <div className="pcard-dots" aria-hidden>
            {dots.map((on, i) => (
              <span key={i} className={on ? "on" : ""} />
            ))}
          </div>
          <div className="pcard-bottom">
            <span className="pcard-holder">{holder}</span>
            <span className="pcard-valid">
              <small>{t("pkg_card_until")}</small>
              {date}
            </span>
          </div>
        </div>
      </div>
      {hint && <p className="pcard-hint">{t("pkg_card_hint")}</p>}
    </div>
  );
}
