import { Coins, Lock } from "lucide-react";

import { useLang, useT } from "../lib/app";
import { formatDate } from "../lib/i18n";
import type { PointsBoxKey, PointsInfo } from "../lib/types";
import { CaseArt, PrizeTile, TIER } from "./PointsCase";

/**
 * Баллы за покупки и три кейса за баллы на вкладке «Пакеты».
 * Кейс открывается отдельной страницей: что внутри, шансы и рулетка (PointsCase.tsx).
 */
export function PointsShop({ info, onSelect }: { info: PointsInfo; onSelect: (key: PointsBoxKey) => void }) {
  const t = useT();
  const { lang } = useLang();
  const max = Math.max(...info.boxes.map((b) => b.price));
  const next = info.boxes.find((b) => b.price > info.points);
  const fill = Math.min(100, (info.points / max) * 100);

  return (
    <div className="pts">
      <div className="pts-head">
        <div>
          <div className="pts-label">{t("pts_balance")}</div>
          <div className="pts-num tabular" data-points-target>
            <Coins size={26} /> {info.points}
          </div>
        </div>
        <div className="pts-rule">{t("pts_rule", { n: info.per_presentation })}</div>
      </div>

      {/* шкала до самого большого кейса, отметки — цены кейсов */}
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

      <div className="pts-cases">
        {info.boxes.map((b) => {
          const can = info.points >= b.price;
          // лучший приз кейса — тот, что реже всего выпадает
          const best = [...b.prizes].sort((x, y) => x.percent - y.percent)[0]!;
          return (
            <button key={b.key} className={`pts-case ${b.key}${can ? " can" : ""}`} onClick={() => onSelect(b.key)}>
              <CaseArt tier={b.key} size={78} />
              <span className="pts-case-name">{t(TIER[b.key])}</span>
              <span className="pts-case-best">
                <PrizeTile p={best} />
              </span>
              <span className="pts-case-price tabular">
                {can ? <Coins size={14} /> : <Lock size={13} />} {b.price}
              </span>
            </button>
          );
        })}
      </div>
      <p className="lucky-note pts-note">{t("pts_note", { days: info.expire_days })}</p>
    </div>
  );
}
