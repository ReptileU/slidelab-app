import { useT } from "../lib/app";

/**
 * Карта скидки из кейса — обычная скидочная карточка-купон, не банковская:
 * яркий фон, крупное −N%, отрывной корешок с перфорацией и штрихкодом.
 * Скидка ложится на следующий заказ, оплаченный деньгами, и не складывается со скидкой первого заказа.
 */
export function DiscountCard({ pct, holder }: { pct: number; holder?: string }) {
  const t = useT();
  const tone = pct >= 50 ? "hot" : pct >= 30 ? "mid" : "cool";
  return (
    <div className={`dtag ${tone}`}>
      <div className="dtag-main">
        <span className="dtag-shine" />
        <span className="dtag-kind">{t("disc_card")}</span>
        <div className="dtag-pct tabular">
          <span className="dtag-minus">−</span>
          {pct}
          <span className="dtag-sign">%</span>
        </div>
        <span className="dtag-for">{t("disc_next_short")}</span>
        {holder && <span className="dtag-holder">{holder}</span>}
      </div>
      <div className="dtag-stub" aria-hidden>
        <span className="dtag-hole" />
        <span className="dtag-brand">SLIDELAB</span>
        <span className="dtag-bars" />
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
