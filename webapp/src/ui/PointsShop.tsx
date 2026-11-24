import { Coins, Lock } from "lucide-react";

import { useLang, useT } from "../lib/app";
import { formatDate, type Key } from "../lib/i18n";
import type { PointsBox, PointsBoxKey, PointsInfo } from "../lib/types";
import { couponWord, pointsWord, presWord } from "../lib/words";

const TIER: Record<PointsBoxKey, Key> = { small: "pts_small", medium: "pts_medium", large: "pts_large" };

function pct(lang: string, v: number): string {
  return `${v.toLocaleString(lang === "en" ? "en-US" : "ru-RU", { maximumFractionDigits: 1 })}%`;
}

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
          : t("pts_row_pack", { n, word: presWord(lang, n) });
}

/**
 * Баллы за покупки и три пакета за баллы на вкладке «Пакеты».
 * Чем дороже пакет, тем крупнее призы — копить выгоднее, чем тратить сразу.
 */
export function PointsShop({
  info,
  onOpen,
  busy,
}: {
  info: PointsInfo;
  onOpen: (key: PointsBoxKey) => void;
  busy: PointsBoxKey | null;
}) {
  const t = useT();
  const { lang } = useLang();
  const name = usePrizeName();
  const max = Math.max(...info.boxes.map((b) => b.price));
  const next = info.boxes.find((b) => b.price > info.points);
  const fill = Math.min(100, (info.points / max) * 100);

  return (
    <div className="pts">
      <div className="pts-head">
        <div>
          <div className="pts-label">{t("pts_balance")}</div>
          <div className="pts-num tabular">
            <Coins size={26} /> {info.points}
          </div>
        </div>
        <div className="pts-rule">{t("pts_rule", { n: info.per_presentation })}</div>
      </div>

      {/* шкала до самого большого пакета, отметки — цены пакетов */}
      <div className="pts-track" aria-hidden>
        <i style={{ width: `${fill}%` }} />
        {info.boxes.map((b) => (
          <span key={b.key} className={info.points >= b.price ? "on" : ""} style={{ left: `${(b.price / max) * 100}%` }}>
            <em className="tabular">{b.price}</em>
          </span>
        ))}
      </div>
      <p className="pts-next">
        {next ? t("pts_to_next", { n: next.price - info.points, price: next.price }) : t("pts_all_open")}
        {info.expire_at && info.points > 0 && <> · {t("pts_expire", { date: formatDate(info.expire_at, lang) })}</>}
      </p>

      <div className="pts-boxes">
        {info.boxes.map((b: PointsBox) => {
          const can = info.points >= b.price;
          const top = Math.max(...b.prizes.map((p) => p.percent));
          return (
            <div key={b.key} className={`pts-box ${b.key}${can ? " can" : ""}`}>
              <div className="pts-box-h">
                <span className="pts-tier">{t(TIER[b.key])}</span>
                <span className="pts-price tabular">
                  <Coins size={14} /> {b.price}
                </span>
              </div>
              <div className="pts-odds">
                {b.prizes.map((p) => (
                  <div key={`${p.prize}${p.value}`} className="pts-row">
                    <span>{name(p.prize, p.value)}</span>
                    <span className="lucky-bar">
                      <i style={{ width: `${Math.max(4, (p.percent / top) * 100)}%` }} />
                    </span>
                    <span className="tabular">{pct(lang, p.percent)}</span>
                  </div>
                ))}
              </div>
              <button className="pts-buy" disabled={!can || busy !== null} onClick={() => onOpen(b.key)}>
                {busy === b.key ? (
                  <span className="btn-spinner" />
                ) : can ? (
                  t("pts_open")
                ) : (
                  <>
                    <Lock size={14} /> {t("pts_need", { n: b.price - info.points })}
                  </>
                )}
              </button>
            </div>
          );
        })}
      </div>
      <p className="lucky-note pts-note">{t("pts_note", { days: info.expire_days })}</p>
    </div>
  );
}
