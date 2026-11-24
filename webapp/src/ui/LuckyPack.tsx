import { Gift, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useCatalog, useLang, useMe, useT } from "../lib/app";
import { money } from "../lib/i18n";
import { playFanfare, playReveal, playTap, unlockAudio } from "../lib/sound";
import { haptic } from "../lib/tg";
import type { BoxPrize, LuckyInfo, LuckyPrize, PlanCode } from "../lib/types";
import { couponWord, pointsWord, presWord } from "../lib/words";
import { Coupon } from "./Coupon";
import { DiscountCard, PointsCoin } from "./Discount";
import { PackCard } from "./PackCard";

/** Выпавший пакет — карта того же тарифа, что начислен на сервере (services/lucky.py, services/points.py). */
const PRIZE_PLAN: Partial<Record<BoxPrize, PlanCode>> = { two: "week", four: "month", vip: "vip" };

export type Rarity = "common" | "rare" | "epic" | "legend";

const CONFETTI: Record<"epic" | "legend", string[]> = {
  epic: ["#c45eff", "#ff5ea8", "#5ea8ff", "#ffffff"],
  legend: ["#ffd24a", "#fff3c4", "#f3b63f", "#ffffff", "#ff9a3d"],
};

/** Вибрация по редкости: легендарный — серия сильных толчков. */
function celebrate(r: Rarity) {
  if (r === "common") return haptic.success();
  const n = r === "rare" ? 2 : r === "epic" ? 3 : 6;
  for (let i = 0; i < n; i++) setTimeout(() => haptic.success(), i * (r === "legend" ? 220 : 160));
}

/** Несколько купонов — стопкой, верхний целиком, под ним торчат остальные. */
export function CouponStack({ n }: { n: number }) {
  const shown = Math.min(n, 4);
  return (
    <div className="cstack" style={{ ["--k" as string]: shown }}>
      {Array.from({ length: shown }, (_, i) => (
        <div key={i} className="cstack-i" style={{ ["--i" as string]: shown - 1 - i }}>
          <Coupon slides="s20" />
        </div>
      ))}
      <span className="cstack-n tabular">×{n}</span>
    </div>
  );
}

const TAPS = 3; // сколько раз нажать, чтобы пакет открылся
const clamp = (v: number) => Math.max(-1, Math.min(1, v));

function percent(lang: string, value: number): string {
  return `${value.toLocaleString(lang === "en" ? "en-US" : "ru-RU", { maximumFractionDigits: 1 })}%`;
}

/** Наклон за пальцем — пакет «живой» и до покупки, и при открытии. */
function useTilt<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const move = (e: React.PointerEvent<T>) => {
    const el = ref.current;
    if (!el) return;
    const box = el.getBoundingClientRect();
    const x = clamp(((e.clientX - box.left) / box.width) * 2 - 1);
    const y = clamp(((e.clientY - box.top) / box.height) * 2 - 1);
    el.style.setProperty("--rx", `${(-y * 9).toFixed(2)}deg`);
    el.style.setProperty("--ry", `${(x * 11).toFixed(2)}deg`);
    el.style.setProperty("--gx", `${(50 + x * 40).toFixed(1)}%`);
    el.style.setProperty("--gy", `${(50 + y * 40).toFixed(1)}%`);
  };
  const reset = () => {
    const el = ref.current;
    if (!el) return;
    for (const name of ["--rx", "--ry"]) el.style.setProperty(name, "0deg");
    el.style.setProperty("--gx", "50%");
    el.style.setProperty("--gy", "50%");
  };
  return { ref, onPointerMove: move, onPointerDown: move, onPointerLeave: reset, onPointerUp: reset, onPointerCancel: reset };
}

/**
 * Карточка бонус-пакета на вкладке «Пакеты»: что это, цена и открытые шансы.
 * Шансы приходят с сервера — те же числа, по которым идёт розыгрыш.
 */
export function LuckyCard({
  info,
  onBuy,
  onOpen,
  preview = false,
}: {
  info: LuckyInfo;
  onBuy: () => void;
  onOpen: () => void;
  /** демо: кнопки ничего не покупают */
  preview?: boolean;
}) {
  const t = useT();
  const { lang } = useLang();
  const tilt = useTilt<HTMLDivElement>();
  const top = Math.max(...info.odds.map((o) => o.percent));
  const price = `${money(info.price)} ${t("sum")}`;

  return (
    <div className="lucky" {...tilt}>
      <div className="lucky-holo" />
      <div className="lucky-glare" />
      <div className="lucky-in">
        <div className="row spread">
          <span className="lucky-badge">
            <Sparkles size={13} /> {t("plan_lucky")}
          </span>
          <span className="lucky-limit">{t("lucky_limit", { n: info.limit })}</span>
        </div>
        <h3 className="lucky-head">{t("lucky_head")}</h3>
        <ol className="lucky-steps">
          <li>
            <b>1</b>
            <span>{t("lucky_s1", { price })}</span>
          </li>
          <li>
            <b>2</b>
            <span>{t("lucky_s2")}</span>
          </li>
          <li>
            <b>3</b>
            <span>{t("lucky_s3")}</span>
          </li>
        </ol>

        <div className="lucky-odds" aria-label={t("lucky_odds")}>
          <div className="lucky-odds-h">{t("lucky_odds")}</div>
          {info.odds.map((o) => (
            <div key={o.prize} className={`lucky-row${o.prize === "vip" ? " vip" : ""}`}>
              <span className="lucky-row-n">
                {o.prize === "one" ? t("lucky_row_coupon") : o.prize === "vip" ? t("lucky_row_vip") : t("lucky_row_pack")}{" "}
                <small>· {o.count}</small>
              </span>
              <span className="lucky-bar">
                <i style={{ width: `${Math.max(3, (o.percent / top) * 100)}%` }} />
              </span>
              <span className="lucky-row-p tabular">{percent(lang, o.percent)}</span>
            </div>
          ))}
        </div>
        <p className="lucky-note">{t("lucky_odds_note")}</p>

        {info.pending ? (
          <button className="lucky-buy open" onClick={onOpen}>
            <span>
              <Gift size={18} /> {t("lucky_open")}
            </span>
          </button>
        ) : (
          <button className="lucky-buy" onClick={onBuy} disabled={!preview && !info.can_buy}>
            <span>{info.can_buy || preview ? t("buy") : t("lucky_limit_hit")}</span>
            {(info.can_buy || preview) && <span className="tabular">{price}</span>}
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Открытие бонус-пакета: по пакету нужно нажать три раза — он трясётся, трескается и раскрывается.
 * Приз уже начислен при оплате; здесь только показываем, что выпало.
 */
export function LuckyReveal({
  prize,
  onDone,
  name,
  points,
  opened = false,
  rarity,
  couponSlides = "s20",
}: {
  prize: LuckyPrize;
  onDone: () => void;
  /** надпись на пакете (по умолчанию — «Бонус-пакет») */
  name?: string;
  /** пакет за баллы: сколько баллов осталось после него */
  points?: number;
  /** сразу показать приз (кейс уже «открылся» рулеткой) */
  opened?: boolean;
  /** редкость приза в кейсе: чем реже, тем громче выпадение */
  rarity?: Rarity;
  /** объём купона (приветственный кейс — 10 слайдов) */
  couponSlides?: "s10" | "s20" | "s30";
}) {
  const t = useT();
  const { lang } = useLang();
  const holder = useMe().data?.first_name || "SlideLab";
  const days: Record<string, number> = Object.fromEntries((useCatalog().data?.plans ?? []).map((p) => [p.code, p.days]));
  const tilt = useTilt<HTMLButtonElement>();
  const [taps, setTaps] = useState(0);
  const [open, setOpen] = useState(opened);
  const big =
    prize.prize === "discount" ? prize.count >= 50 : prize.prize === "points" ? false : prize.count >= (prize.prize === "coupons" ? 5 : 4);
  const plan = PRIZE_PLAN[prize.prize];

  // легендарный приз показывается не сразу: сначала темнеет экран и бьёт столб света
  const [shown, setShown] = useState(rarity !== "legend");
  useEffect(() => {
    if (!opened) return;
    if (rarity) {
      playFanfare(rarity);
      celebrate(rarity);
    } else playReveal(big);
    if (rarity === "legend") {
      const id = setTimeout(() => setShown(true), 1300);
      return () => clearTimeout(id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const tier = rarity ?? (big ? "epic" : "common");
  // чтобы случайное касание в момент выпадения не закрыло показ раньше времени
  const [canClose, setCanClose] = useState(false);
  useEffect(() => {
    if (!open || !shown) return;
    const id = setTimeout(() => setCanClose(true), 900);
    return () => clearTimeout(id);
  }, [open, shown]);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  function tap() {
    if (open) return;
    unlockAudio();
    const next = taps + 1;
    setTaps(next);
    if (next < TAPS) {
      playTap(next);
      haptic.tap();
      return;
    }
    playTap(next);
    haptic.success();
    setTimeout(() => {
      setOpen(true);
      playReveal(big);
      if (big) setTimeout(() => haptic.success(), 260);
    }, 380);
  }

  return createPortal(
    <div
      onClick={() => {
        // приз уже начислен — закрыть можно касанием в любом месте, когда анимация отыграла
        if (open && shown && canClose) onDone();
      }}
      className={`lr${open ? " open" : ""}${big || rarity === "epic" || rarity === "legend" ? " big" : ""} r-${tier}${shown ? " shown" : ""}`}
      role="dialog"
      aria-modal="true"
    >
      <div className="lr-rays" />
      {open && tier !== "common" && <div className="lr-flash" />}
      {open && (tier === "epic" || tier === "legend") && <div className="lr-wave" />}
      {open && tier === "legend" && (
        <>
          <div className="lr-beam" />
          <div className="lr-coins" aria-hidden>
            {Array.from({ length: 26 }, (_, i) => (
              <i key={i} style={{ ["--x" as string]: `${(i * 37) % 100}%`, ["--d" as string]: `${1.2 + ((i * 53) % 17) / 10}s`, ["--w" as string]: `${(i * 29) % 1500}ms` }} />
            ))}
          </div>
        </>
      )}
      {open && shown && (tier === "epic" || tier === "legend") && (
        <div className="lr-confetti" aria-hidden>
          {Array.from({ length: tier === "legend" ? 60 : 36 }, (_, i) => (
            <i
              key={i}
              style={{
                ["--x" as string]: `${(i * 61) % 100}vw`,
                ["--r" as string]: `${(i * 47) % 360}deg`,
                ["--d" as string]: `${(i * 37) % 900}ms`,
                ["--t" as string]: `${2.2 + ((i * 13) % 14) / 10}s`,
                ["--c" as string]: CONFETTI[tier][i % CONFETTI[tier].length],
              }}
            />
          ))}
        </div>
      )}
      {!open ? (
        <>
          <button
            key={taps}
            className={`lr-pack t${Math.min(taps, TAPS)}`}
            {...tilt}
            onClick={tap}
            aria-label={t("lucky_open")}
          >
            <span className="lr-foil" />
            <span className="lr-glare" />
            <span className="lr-crack c1" />
            <span className="lr-crack c2" />
            <span className="lr-crack c3" />
            <span className="lr-label">
              <b>S</b> SlideLab
            </span>
            <span className="lr-mark">?</span>
            <span className="lr-name">{name ?? t("plan_lucky")}</span>
          </button>
          <div className="lr-steps" aria-hidden>
            {Array.from({ length: TAPS }, (_, i) => (
              <i key={i} className={i < taps ? "on" : ""} />
            ))}
          </div>
          <p className="lr-hint">{t("lucky_tap")}</p>
        </>
      ) : (
        <>
          <div className="lr-sparks" aria-hidden>
            {Array.from({ length: big ? 22 : 12 }, (_, i) => (
              <i key={i} style={{ ["--a" as string]: `${(360 / (big ? 22 : 12)) * i}deg`, ["--d" as string]: `${(i % 5) * 40}ms` }} />
            ))}
          </div>
          <div className="lr-prize">
            <div className="lr-got">{t("lucky_got")}</div>
            {rarity && rarity !== "common" && <div className={`lr-rarity ${rarity}`}>{t(`rar_${rarity}`)}</div>}
            {/* что выпало — сразу той карточкой, что ляжет в кошелёк: купон или карта пакета */}
            <div className="lr-card">
              {prize.prize === "one" ? (
                <Coupon slides={couponSlides} />
              ) : prize.prize === "coupons" ? (
                <CouponStack n={prize.count} />
              ) : prize.prize === "discount" ? (
                <DiscountCard pct={prize.count} holder={holder} />
              ) : prize.prize === "points" ? (
                <PointsCoin value={prize.count} size={150} />
              ) : plan ? (
                <PackCard
                  pkg={{
                    plan,
                    left: prize.count,
                    total: prize.count,
                    expires_at: new Date(Date.now() + (days[plan] ?? 30) * 864e5).toISOString(),
                  }}
                  holder={holder}
                  hint={false}
                  still
                />
              ) : null}
            </div>
            <div className="lr-unit">
              {prize.prize === "one"
                ? t("lucky_got_coupon")
                : prize.prize === "coupons"
                  ? t("pts_got_coupons", { n: prize.count, word: couponWord(lang, prize.count) })
                  : prize.prize === "discount"
                    ? t("pts_got_discount", { n: prize.count })
                    : prize.prize === "points"
                      ? t("pts_got_points", { n: prize.count, word: pointsWord(lang, prize.count) })
                      : t(prize.prize === "vip" ? "lucky_got_vip" : "lucky_got_pack", { n: prize.count, word: presWord(lang, prize.count) })}
            </div>
            {points !== undefined && <div className="lr-left">{t("pts_left", { n: points })}</div>}
          </div>
          <p className="lr-anywhere">{t("lucky_anywhere")}</p>
        </>
      )}
    </div>,
    document.body,
  );
}
