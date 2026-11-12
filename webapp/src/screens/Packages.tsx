import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../lib/api";
import { useCatalog, useLang, useMe, useT } from "../lib/app";
import { formatDate, money, type Key } from "../lib/i18n";
import type { Plan } from "../lib/types";
import { Section, Skeleton, Toast } from "../ui";
import { PaySheet } from "../ui/PaySheet";

/** Картинка-фон пакета: чем дороже пакет, тем статуснее (серебро → платина → золото). */
const PACK_ART: Record<string, string> = { week: "p0", month: "p1b", vip: "p2" };

/** «2 презентации», «10 презентаций» — подпись под крупной цифрой. */
function presWord(lang: string, n: number): string {
  if (lang === "uz") return "taqdimot";
  if (lang === "en") return n === 1 ? "presentation" : "presentations";
  const d = n % 10;
  const dd = n % 100;
  if (d === 1 && dd !== 11) return "презентация";
  if (d >= 2 && d <= 4 && (dd < 12 || dd > 14)) return "презентации";
  return "презентаций";
}

export function Packages() {
  const t = useT();
  const { lang } = useLang();
  const qc = useQueryClient();
  const me = useMe();
  const catalog = useCatalog();
  const [buying, setBuying] = useState<Plan | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const pkg = me.data?.package;
  const c = catalog.data;
  const planName = (code: string) => t(`plan_${code}` as Key);

  return (
    <div className="page">
      <h1 className="large-title" style={{ margin: "8px 0 8px" }}>
        {t("packages_t")}
      </h1>
      <p className="subhead secondary" style={{ margin: "0 0 24px" }}>
        {t("packages_x")}
      </p>

      {pkg && (
        <Section title={t("pkg_my")}>
          <div className="card">
            <div className="row spread">
              <span className="headline">{planName(pkg.plan)}</span>
              <span className="footnote secondary">{t("pkg_until", { date: formatDate(pkg.expires_at, lang) })}</span>
            </div>
            <div className="title1 tabular mt-8">{t("pkg_left", { left: pkg.left, total: pkg.total })}</div>
            <div className="progress mt-8">
              <i style={{ width: `${(pkg.left / Math.max(pkg.total, 1)) * 100}%` }} />
            </div>
          </div>
        </Section>
      )}

      <Section footer={t("pkg_note")}>
        <div className="stack gap-12">
          {!c && [0, 1, 2].map((i) => <Skeleton key={i} height={230} radius={24} />)}
          {c?.plans.map((p) => {
            const single = c.prices.s20 * p.count;
            const save = Math.round((1 - p.price / single) * 100);
            const perks = [p.notes_free && t("pkg_notes"), p.priority && t("pkg_priority")].filter(Boolean);
            return (
              <div key={p.code} className={`pack pack-${p.code}`}>
                <img className="pack-bg" src={`./packs/${PACK_ART[p.code] ?? "p0"}.webp`} alt="" draggable={false} />
                <div className="pack-body">
                  <div className="row" style={{ gap: 6 }}>
                    {p.code === "vip" && <span className="pack-chip vip">VIP</span>}
                    <span className="pack-chip">{t("pkg_save", { pct: save })}</span>
                    <span className="pack-chip ghost">{t("pkg_days", { days: p.days })}</span>
                  </div>
                  <div className="pack-count">
                    <span className="pack-num tabular">{p.count}</span>
                    <span className="pack-unit">{presWord(lang, p.count)}</span>
                  </div>
                  <div className="pack-per">
                    {t("per_one", { price: `${money(Math.round(p.price / p.count))} ${t("sum")}` })}
                  </div>
                  {perks.length > 0 && <div className="pack-perks">{perks.join(" · ")}</div>}
                  <button className="pack-buy" onClick={() => setBuying(p)}>
                    <span>{t("buy")}</span>
                    <span className="tabular">
                      {money(p.price)} {t("sum")}
                    </span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </Section>

      <PaySheet
        open={!!buying}
        title={buying ? planName(buying.code) : ""}
        amount={buying?.price ?? 0}
        onClose={() => setBuying(null)}
        createInvoice={(provider) => api.packageInvoice(buying!.code, provider)}
        sendReceipt={(image) => api.packageReceipt(buying!.code, image)}
        onReceipt={() => setToast(t("pay_shot_sent"))}
        onPaid={() => {
          setToast(t("pay_pkg_ok"));
          setTimeout(() => qc.invalidateQueries({ queryKey: ["me"] }), 1500);
        }}
      />
      <Toast text={toast} onDone={() => setToast(null)} />
    </div>
  );
}
