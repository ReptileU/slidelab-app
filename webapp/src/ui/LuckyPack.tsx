import { Gift, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useLang, useT } from "../lib/app";
import { money } from "../lib/i18n";
import { playReveal, playTap, unlockAudio } from "../lib/sound";
import { haptic } from "../lib/tg";
import type { LuckyInfo, LuckyPrize } from "../lib/types";
import { presWord } from "../lib/words";

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
                {o.prize === "vip" ? `VIP · ${o.count}` : o.count}
                {o.prize !== "vip" && <small> {presWord(lang, o.count)}</small>}
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
export function LuckyReveal({ prize, onDone }: { prize: LuckyPrize; onDone: () => void }) {
  const t = useT();
  const { lang } = useLang();
  const tilt = useTilt<HTMLButtonElement>();
  const [taps, setTaps] = useState(0);
  const [open, setOpen] = useState(false);
  const big = prize.count >= 4;

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
    <div className={`lr${open ? " open" : ""}${big ? " big" : ""}`} role="dialog" aria-modal="true">
      <div className="lr-rays" />
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
            <span className="lr-name">{t("plan_lucky")}</span>
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
            {prize.prize === "vip" && <div className="lr-vip">{t("lucky_vip")}</div>}
            <div className="lr-num tabular silver-text">{prize.count}</div>
            <div className="lr-unit">{presWord(lang, prize.count)}</div>
          </div>
          <button className="lr-take" onClick={onDone}>
            {t("lucky_take")}
          </button>
        </>
      )}
    </div>,
    document.body,
  );
}
