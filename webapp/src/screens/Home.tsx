import { Gift } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useCatalog, useMe, useOrders, useT } from "../lib/app";
import { money, type Key } from "../lib/i18n";
import { hintKey, STATUS_BADGE, statusKey } from "../lib/order";
import { haptic } from "../lib/tg";
import { Img, Logo, PriceTag, Section, Skeleton, useGlare } from "../ui";
import { PackCard } from "../ui/PackCard";
import { WorksCarousel } from "../ui/WorksCarousel";

export function Home() {
  const t = useT();
  const nav = useNavigate();
  const glare = useGlare();
  const me = useMe();
  const catalog = useCatalog();
  const orders = useOrders();
  const active = orders.data?.find((o) => !["done", "cancelled"].includes(o.status));
  const c = catalog.data;
  const first = me.data?.first_order_price ?? null;

  const returning = !!me.data?.package || (orders.data?.length ?? 0) > 0;

  return (
    <div className="page home">
      {/* 1. Своё: карта пакета и текущий заказ — первое, что видит постоянный клиент */}
      {me.data?.package && (
        <Section title={t("pkg_my")} action={{ label: t("pkg_all"), onClick: () => nav("/packages") }}>
          <PackCard pkg={me.data.package} holder={me.data.first_name || "SlideLab"} />
        </Section>
      )}

      {active && (
        <Section title={t("active_t")}>
          <button className="card" onClick={() => nav(`/orders/${active.id}`)}>
            <div className="row spread">
              <span className="footnote secondary">{t("order_n", { id: active.id })}</span>
              <span className={`badge ${STATUS_BADGE[active.status]}`}>{t(statusKey(active.status))}</span>
            </div>
            <div className="headline mt-8 ellipsis">{active.topic}</div>
            <div className="subhead secondary">{t(hintKey(active.status))}</div>
          </button>
        </Section>
      )}

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
        <button className="btn btn-inverse" onClick={() => go("ours")}>
          {t("cta_order")}
        </button>
        <button className="hero-link" onClick={() => go("own")}>
          {t("own_link")} ›
        </button>
        {first && c && first < c.prices.s10 && (
          <div className="offer">
            <div className="offer-t">
              <Gift size={14} /> {t("first_badge")} · {t("slides_s10")}
            </div>
            <div style={{ marginTop: 4 }}>
              <PriceTag big now={money(first)} old={money(c.prices.s10)} sum={t("sum")} />
            </div>
            <div className="offer-s">{t("price_first")}</div>
          </div>
        )}
      </header>

      {/* 3. Доказательства: работы и стили */}
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
