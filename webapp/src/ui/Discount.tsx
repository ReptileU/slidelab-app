import { useT } from "../lib/app";

/**
 * Карта скидки из пакета за баллы: тёмная «металлическая» карта с голограммой и крупным −N%.
 * Скидка ложится на следующий заказ, оплаченный деньгами, и не складывается со скидкой первого заказа.
 */
export function DiscountCard({ pct, holder }: { pct: number; holder?: string }) {
  const t = useT();
  return (
    <div className={`dcard${pct >= 50 ? " hot" : ""}`}>
      <span className="dcard-holo" />
      <span className="dcard-shine" />
      <div className="dcard-top">
        <span className="dcard-kind">{t("disc_card")}</span>
        <span className="dcard-chip" aria-hidden />
      </div>
      <div className="dcard-pct tabular">
        <span className="dcard-minus">−</span>
        {pct}
        <span className="dcard-sign">%</span>
      </div>
      <div className="dcard-bottom">
        <span>{holder ? holder.toUpperCase() : t("disc_next")}</span>
        <b>SLIDELAB</b>
      </div>
    </div>
  );
}

/** Монета-баллы: для выигрыша «+N баллов» и для счёта в профиле. */
export function PointsCoin({ value, size = 120 }: { value: number; size?: number }) {
  return (
    <div className="pcoin" style={{ ["--s" as string]: `${size}px` }}>
      <span className="pcoin-rim" />
      <span className="pcoin-face tabular">+{value}</span>
      <span className="pcoin-shine" />
    </div>
  );
}
