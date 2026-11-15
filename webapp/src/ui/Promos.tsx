import { useNavigate } from "react-router-dom";

import { useCatalog, useMe, useT } from "../lib/app";
import { money } from "../lib/i18n";
import { haptic } from "../lib/tg";

/**
 * Рекламные плитки на главной: скидка на первую презентацию, пакеты, бонус-пакет, бесплатная обложка.
 * Цифры берутся из прайса — плитка не обещает того, чего нет в приложении.
 */
export function Promos() {
  const t = useT();
  const nav = useNavigate();
  const me = useMe();
  const c = useCatalog().data;
  if (!c) return null;

  const first = me.data?.first_order_price ?? null;
  const firstPct = first && first < c.prices.s10 ? Math.round((1 - first / c.prices.s10) * 100) : 0;
  const packPct = Math.max(0, ...c.plans.map((p) => Math.round((1 - p.price / (c.prices.s20 * p.count)) * 100)));
  const go = (to: string) => {
    haptic.tap();
    nav(to);
  };

  return (
    <div className="promos hscroll" aria-label={t("promo_t")}>
      {first !== null && firstPct > 0 && (
        <button className="promo promo-first" onClick={() => go("/order?design=ours")}>
          <span className="promo-big">−{firstPct}%</span>
          <span className="promo-text">{t("promo_first", { price: `${money(first)} ${t("sum")}` })}</span>
        </button>
      )}
      {packPct > 0 && (
        <button className="promo promo-packs" onClick={() => go("/packages")}>
          <img src="./packs/p1b.webp" alt="" draggable={false} />
          <span className="promo-big">
            <small>{t("promo_upto")}</small>−{packPct}%
          </span>
          <span className="promo-text">{t("promo_packs")}</span>
        </button>
      )}
      <button className="promo promo-lucky" onClick={() => go("/packages?lucky=1")}>
        <i className="promo-holo" />
        <span className="promo-big silver-text">1→10</span>
        <span className="promo-text">{t("promo_lucky")}</span>
      </button>
      <button className="promo promo-cover" onClick={() => go("/order?design=ours")}>
        <span className="promo-big">
          0 <small>{t("sum")}</small>
        </span>
        <span className="promo-text">{t("promo_cover")}</span>
      </button>
    </div>
  );
}
