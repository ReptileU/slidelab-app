import { Coins, Lock, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { ApiError } from "../lib/api";
import { useLang, useT } from "../lib/app";
import type { Key } from "../lib/i18n";
import { playTick, unlockAudio } from "../lib/sound";
import { alert, haptic } from "../lib/tg";
import type { BoxPrize, PointsBox, PointsBoxKey, PointsResult } from "../lib/types";
import { LuckyReveal, type Rarity } from "./LuckyPack";
import { couponWord, pointsWord, presWord } from "../lib/words";

export const TIER: Record<PointsBoxKey, Key> = {
  small: "pts_small",
  medium: "pts_medium",
  large: "pts_large",
  welcome: "pts_welcome",
};

type Prize = PointsBox["prizes"][number];

/** Название приза одной строкой: «3 купона», «Пакет · 4 презентации», «Скидка 30%», «+60 баллов». */
export function usePrizeName() {
  const t = useT();
  const { lang } = useLang();
  return (prize: string, n: number) =>
    prize === "one" || prize === "coupons"
      ? `${n} ${couponWord(lang, n)}`
      : prize === "discount"
        ? t("pts_row_discount", { n })
        : prize === "points"
          ? `+${n} ${pointsWord(lang, n)}`
          : prize === "vip"
            ? t("pts_row_vip", { n })
            : t("pts_row_pack", { n, word: presWord(lang, n) });
}

/** Редкость по шансу — цвет полоски у ячейки, как в кейсах. */
function rarity(percent: number): Rarity {
  return percent >= 30 ? "common" : percent >= 15 ? "rare" : percent >= 7 ? "epic" : "legend";
}

/** Сам приз маленькой картинкой: карта скидки, купон, пакет, монета. */
function PrizeArt({ prize, value }: { prize: BoxPrize; value: number }) {
  if (prize === "discount")
    return (
      <span className={`pa-disc ${value >= 50 ? "hot" : value >= 30 ? "mid" : "cool"}`}>
        −{value}%<i />
      </span>
    );
  if (prize === "one" || prize === "coupons")
    return (
      <span className="pa-coupon">
        <span className="pa-coupon-t" />
        {value > 1 && <span className="pa-coupon-t b" />}
        <b>×{value}</b>
      </span>
    );
  if (prize === "points") return <span className="pa-coin">+{value}</span>;
  return (
    <span className={`pa-pack ${prize}`}>
      <b>{value}</b>
      <em>SLIDELAB</em>
    </span>
  );
}

export function PrizeTile({ p, label }: { p: Prize; label?: string }) {
  return (
    <div className={`ptile ${rarity(p.percent)}`}>
      <div className="ptile-art">
        <PrizeArt prize={p.prize} value={p.value} />
      </div>
      {label && <div className="ptile-name">{label}</div>}
    </div>
  );
}

/** Обложка кейса: коробка с крышкой в цвете уровня. */
export function CaseArt({ tier, size = 96, shake = false }: { tier: PointsBoxKey; size?: number; shake?: boolean }) {
  return (
    <span className={`chest ${tier}${shake ? " shake" : ""}`} style={{ ["--cs" as string]: `${size}px` }} aria-hidden>
      <span className="chest-rays" />
      <span className="chest-glow" />
      <img src={`./cases/case-${CASE_IMG[tier]}.webp`} alt="" draggable={false} />
      <span className="chest-spark s1" />
      <span className="chest-spark s2" />
      <span className="chest-spark s3" />
    </span>
  );
}

const CASE_IMG: Record<PointsBoxKey, string> = { small: "bronze", medium: "silver", large: "gold", welcome: "gold" };

const CELL = 112; // ширина ячейки ленты + зазор, px
const WIN_AT = 42; // на какой ячейке остановится лента
const LENGTH = 50;
// чем реже приз, тем дольше лента тянет — больше напряжения перед остановкой
const SPIN_MS: Record<Rarity, number> = { common: 5600, rare: 6000, epic: 6600, legend: 7600 };

function pick(prizes: Prize[]): Prize {
  let r = Math.random() * 100;
  for (const p of prizes) {
    r -= p.percent;
    if (r <= 0) return p;
  }
  return prizes[prizes.length - 1]!;
}

/**
 * Страница кейса: что может выпасть (картинками, с шансами) и рулетка.
 * Приз решает сервер — лента просто собирается так, чтобы под стрелкой остановился именно он.
 */
export function CaseSheet({
  box,
  points,
  onOpen,
  onClose,
}: {
  box: PointsBox;
  points: number;
  onOpen: () => Promise<PointsResult>;
  onClose: (opened: boolean) => void;
}) {
  const t = useT();
  const name = usePrizeName();
  const { lang } = useLang();
  const [result, setResult] = useState<PointsResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [spinning, setSpinning] = useState(false);
  const [reveal, setReveal] = useState(false);
  const [shift, setShift] = useState(0);
  const winRef = useRef<HTMLDivElement>(null);
  const stripRef = useRef<HTMLDivElement>(null);
  const can = points >= box.price;
  const won = result && (box.prizes.find((p) => p.prize === result.prize && p.value === result.value) ?? null);
  const winRarity: Rarity = won ? rarity(won.percent) : "common";
  const spinMs = SPIN_MS[winRarity];

  // до открытия лента — случайные призы этого кейса; после ответа сервера на WIN_AT кладём выпавший
  const idle = useMemo(() => Array.from({ length: LENGTH }, () => pick(box.prizes)), [box]);
  const strip = useMemo(() => {
    if (!result) return idle;
    const won = box.prizes.find((p) => p.prize === result.prize && p.value === result.value) ?? {
      prize: result.prize,
      value: result.value,
      percent: 1,
    };
    const s = [...idle];
    s[WIN_AT] = won;
    return s;
  }, [idle, result, box]);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  // щелчки на каждой проехавшей ячейке, пока лента крутится
  useEffect(() => {
    if (!spinning) return;
    let raf = 0;
    let last = 0;
    const loop = () => {
      const el = stripRef.current;
      if (el) {
        const x = -new DOMMatrixReadOnly(getComputedStyle(el).transform).m41;
        const cell = Math.floor(x / CELL);
        if (cell !== last) {
          last = cell;
          playTick();
          haptic.select();
        }
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [spinning]);

  async function open() {
    if (busy || result) return;
    unlockAudio();
    haptic.tap();
    setBusy(true);
    try {
      const r = await onOpen();
      setResult(r);
      const hit = box.prizes.find((p) => p.prize === r.prize && p.value === r.value);
      const r2: Rarity = hit ? rarity(hit.percent) : "common";
      const w = winRef.current?.clientWidth ?? 360;
      // центр выпавшей ячейки — под стрелкой, со случайным сдвигом внутри ячейки (чтобы не было «ровно по центру»)
      const jitter = (Math.random() - 0.5) * (CELL - 30);
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          setSpinning(true);
          setShift(WIN_AT * CELL + CELL / 2 - w / 2 + jitter);
        }),
      );
      setTimeout(() => {
        setSpinning(false);
        haptic.success();
        // редкий приз сначала подсвечивается на ленте, и только потом — большой показ
        setTimeout(() => setReveal(true), r2 === "legend" ? 1400 : r2 === "epic" ? 1000 : 650);
      }, SPIN_MS[r2] + 80);
    } catch (e) {
      setBusy(false);
      await alert(e instanceof ApiError ? e.message : t("error"));
    }
  }

  return createPortal(
    <div className={`case-sheet ${box.key}`} role="dialog" aria-modal="true">
      <div className="case-top">
        <button className="case-x" onClick={() => !spinning && onClose(!!result)} aria-label={t("close")}>
          <X size={20} />
        </button>
        <span className="case-balance tabular" style={box.price === 0 ? { visibility: "hidden" } : undefined}>
          <Coins size={16} /> {result && reveal ? result.points : result ? points - box.price : points}
        </span>
      </div>

      <div className="case-hero">
        <CaseArt tier={box.key} size={190} shake={busy && !spinning && !result} />
        <h2>{t(TIER[box.key])}</h2>
      </div>

      <div
        className={`case-roll${spinning ? " spin" : ""}${result && !spinning ? ` done r-${winRarity}` : ""}`}
        ref={winRef}
      >
        <div
          className="case-strip"
          ref={stripRef}
          style={{
            transform: `translate3d(${-shift}px,0,0)`,
            transition: shift ? `transform ${spinMs}ms cubic-bezier(.08,.6,.12,1)` : "none",
          }}
        >
          {strip.map((p, i) => (
            <div key={i} className={`case-cell${result && i === WIN_AT && !spinning ? " win" : ""}`}>
              <PrizeTile p={p} />
            </div>
          ))}
        </div>
        <span className="case-arrow top" />
        <span className="case-arrow bottom" />
      </div>

      <button className="case-open" disabled={!can || busy} onClick={() => void open()}>
        {busy && !result ? (
          <span className="btn-spinner" />
        ) : result ? (
          spinning ? t("case_rolling") : name(result.prize, result.value)
        ) : can && box.price === 0 ? (
          t("case_open_free")
        ) : can ? (
          <>
            {t("case_open")} · <Coins size={16} /> {box.price}
          </>
        ) : (
          <>
            <Lock size={16} /> {t("pts_need", { n: box.price - points })}
          </>
        )}
      </button>

      <div className="case-contents">
        <div className="case-h">{t("case_inside")}</div>
        <div className="case-grid">
          {box.prizes.map((p) => (
            <div key={`${p.prize}${p.value}`} className="case-item">
              <PrizeTile p={p} label={name(p.prize, p.value)} />
              <span className="case-pct tabular">
                {p.percent.toLocaleString(lang === "en" ? "en-US" : "ru-RU", { maximumFractionDigits: 1 })}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {reveal && result && (
        <LuckyReveal
          opened
          rarity={winRarity}
          couponSlides={box.key === "welcome" ? "s10" : "s20"}
          prize={{ prize: result.prize, count: result.value }}
          name={t(TIER[box.key])}
          points={box.price ? result.points : undefined}
          onDone={() => onClose(true)}
        />
      )}
    </div>,
    document.body,
  );
}
