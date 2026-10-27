import { CreditCard, Gift, Layers, PenLine, Sparkles, Upload } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useCatalog, useMe, useOrders, useT } from "../lib/app";
import { money } from "../lib/i18n";
import { hintKey, slidesKey, STATUS_BADGE, statusKey, TIERS, tierPrice } from "../lib/order";
import { haptic } from "../lib/tg";
import { Cell, Group, Img, Section, Skeleton, useGlare } from "../ui";

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

  return (
    <div className="page">
      <header className="hero" style={{ margin: "8px 0 28px" }} onPointerMove={glare} onPointerDown={glare}>
        <div className="footnote eyebrow" style={{ fontWeight: 600, letterSpacing: 3 }}>
          SLIDELAB
        </div>
        <h1 className="large-title mt-8 silver-text">{t("hero_title")}</h1>
        <p className="subhead" style={{ margin: "10px 0 22px" }}>
          {t("hero_sub")}
        </p>
        <button className="btn btn-inverse" onClick={() => go("ours")}>
          {t("cta_order")}
        </button>
        {first && (
          <div className="center" style={{ marginTop: 14 }}>
            <span className="badge gold">
              <Gift size={13} /> {t("first_badge", { price: `${money(first)} ${t("sum")}` })}
            </span>
          </div>
        )}
      </header>

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

      <Section>
        <div className="way-grid">
          <button className="card way" onClick={() => go("ours")}>
            <span className="way-icon">
              <Sparkles />
            </span>
            <span className="headline">{t("way_ours_t")}</span>
            <span className="footnote secondary">{t("way_ours_x")}</span>
          </button>
          <button className="card way" onClick={() => go("own")}>
            <span className="way-icon">
              <Upload />
            </span>
            <span className="headline">{t("way_own_t")}</span>
            <span className="footnote secondary">{t("way_own_x")}</span>
          </button>
        </div>
      </Section>

      <Section title={t("works_t")} large>
        <div className="hscroll">
          {c
            ? c.works.map((w) => (
                <figure key={w.image} className="work" style={{ margin: 0 }}>
                  <Img src={w.image} alt={w.title} />
                  <figcaption className="work-caption">
                    <div className="subhead" style={{ fontWeight: 600 }}>
                      {w.title}
                    </div>
                    <div className="footnote secondary">{w.style}</div>
                  </figcaption>
                </figure>
              ))
            : [0, 1].map((i) => (
                <div key={i} className="work">
                  <Skeleton height={180} />
                </div>
              ))}
        </div>
      </Section>

      <Section title={t("styles_t")} large action={{ label: t("styles_all"), onClick: () => nav("/styles") }}>
        <div className="style-grid">
          {c?.styles.slice(5, 9).map((s) => (
            <button key={s.key} className="style-card" onClick={() => nav(`/styles?open=${s.key}`)}>
              <Img src={s.images[0]} alt={s.name} />
              <div className="name">{s.name}</div>
              <div className="hint">{s.hint}</div>
            </button>
          ))}
        </div>
      </Section>

      <Section title={t("how_t")} large>
        <Group icons>
          <Cell icon={<PenLine />} title={t("how_1")} subtitle={t("how_1x")} />
          <Cell icon={<Sparkles />} title={t("how_2")} subtitle={t("how_2x")} />
          <Cell icon={<CreditCard />} title={t("how_3")} subtitle={t("how_3x")} />
          <Cell icon={<Layers />} title={t("how_4")} subtitle={t("how_4x")} />
        </Group>
      </Section>

      {c && (
        <Section title={t("prices_t")} large footer={`${t("x_text")} +${money(c.prices.extra_text)} · ${t("x_notes")} +${money(c.prices.extra_notes)} · ${t("dl_urgent")} +${c.prices.urgent_pct}%`}>
          <Group>
            {TIERS.map((tier) => (
              <Cell
                key={tier}
                title={t(slidesKey(tier))}
                value={`${money(tierPrice(c.prices, tier, first))} ${t("sum")}`}
                onClick={() => nav("/order")}
              />
            ))}
            <Cell title={t("pkg_promo")} chevron onClick={() => nav("/packages")} />
          </Group>
        </Section>
      )}
    </div>
  );

  function go(design: "ours" | "own") {
    haptic.tap();
    nav(`/order?design=${design}`);
  }
}
