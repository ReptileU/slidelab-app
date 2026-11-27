import { Ticket } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useCatalog, useMe, useOrders, useT } from "../lib/app";
import type { Key } from "../lib/i18n";
import { haptic } from "../lib/tg";
import { Img, Logo, Section, Skeleton, useGlare } from "../ui";
import { FriendGift } from "../ui/FriendGift";
import { Promos } from "../ui/Promos";
import { WorksCarousel } from "../ui/WorksCarousel";

export function Home() {
  const t = useT();
  const nav = useNavigate();
  const glare = useGlare();
  const me = useMe();
  const catalog = useCatalog();
  const orders = useOrders();
  const c = catalog.data;

  const returning = !!me.data?.package || (orders.data?.length ?? 0) > 0;

  return (
    <div className="page home">
      {/* Текущий заказ показывает плашка над меню (NowBar) */}
      {/* 2. Главное действие */}
      <header
        className={`hero${returning ? " compact" : ""}`}
        style={{ margin: "8px 0 32px" }}
        onPointerMove={glare}
        onPointerDown={glare}
      >
        {!returning && <Logo />}
        <h1 className={`${returning ? "title1" : "large-title mt-8"} silver-text`}>{t(returning ? "hero_again" : "hero_title")}</h1>
        <p className="subhead" style={{ margin: "10px 0 22px" }}>
          {t("hero_sub")}
        </p>
        {/* Отменённый оплаченный заказ — прямо в главной карточке, без отдельной плашки с ещё одной «Заказать» */}
        {!!me.data?.vouchers && (
          <div className="hero-voucher">
            <Ticket size={18} />
            <span>
              {me.data.vouchers === 1 ? t("voucher_card_one") : t("voucher_card_many", { n: me.data.vouchers })}
              <small>{t("voucher_hero_s")}</small>
            </span>
          </div>
        )}
        <button className="btn btn-inverse" onClick={() => go("ours")}>
          {t("cta_order")}
        </button>
        <button className="btn hero-free" onClick={() => nav("/cover")}>
          <span className="hero-free-tag">0 {t("sum")}</span>
          {t("qc_entry")}
        </button>
        <button className="hero-link" onClick={() => go("own")}>
          {t("own_link")} ›
        </button>
        <button className="hero-link" onClick={() => nav("/builder")}>
          {t("b_entry")} ›
        </button>
      </header>

      {/* пришёл по ссылке друга — показываем его подарок */}
      <FriendGift />

      {/* 3. Рекламные плитки: первая презентация, пакеты, кейсы за баллы */}
      <Promos />

      {/* 4. Доказательства: работы и стили */}
      <Section title={t("works_t")} large>
        {c ? <WorksCarousel works={c.works} /> : <Skeleton height={220} />}
      </Section>

      <Section title={t("styles_t")} large action={{ label: t("styles_all"), onClick: () => nav("/styles") }}>
        <div className="hscroll styles-row">
          {c
            ? c.styles.slice(0, 8).map((s) => (
                <button key={s.key} className="style-card" onClick={() => nav(`/styles?open=${s.key}`)}>
                  <Img src={s.images[0]} alt={s.name} />
                  <div className="name">{s.name}</div>
                  <div className="hint">{s.hint}</div>
                </button>
              ))
            : [0, 1, 2].map((i) => <Skeleton key={i} height={120} />)}
        </div>
      </Section>

      {/* 4. Как это работает — только новым клиентам */}
      {!returning && (
        <Section title={t("how_t")} large>
          <div className="steps">
            {(["1", "2", "3", "4"] as const).map((n) => (
              <div key={n} className="step">
                <span className="step-n">{n}</span>
                <div className="subhead" style={{ fontWeight: 600 }}>
                  {t(`how_${n}` as Key)}
                </div>
                <div className="footnote secondary">{t(`how_${n}x` as Key)}</div>
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  );

  function go(design: "ours" | "own") {
    haptic.tap();
    nav(`/order?design=${design}`);
  }
}
