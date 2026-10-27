import { useQueryClient } from "@tanstack/react-query";
import { Crown, Sparkles, Zap } from "lucide-react";
import { useState } from "react";

import { api } from "../lib/api";
import { useCatalog, useLang, useMe, useT } from "../lib/app";
import { formatDate, money, type Key } from "../lib/i18n";
import type { Plan } from "../lib/types";
import { Button, Section, Skeleton, Toast } from "../ui";
import { PaySheet } from "../ui/PaySheet";

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
          {!c && [0, 1, 2].map((i) => <Skeleton key={i} height={150} radius={16} />)}
          {c?.plans.map((p) => {
            const single = c.prices.s20 * p.count;
            const save = Math.round((1 - p.price / single) * 100);
            const Icon = p.code === "vip" ? Crown : p.code === "month" ? Sparkles : Zap;
            return (
              <div key={p.code} className={`card${p.code === "vip" ? " vip" : ""}`}>
                <div className="row spread">
                  <span className="row" style={{ gap: 10 }}>
                    <span className="way-icon">
                      <Icon />
                    </span>
                    <span className="headline">{planName(p.code)}</span>
                  </span>
                  <span className={`badge ${p.code === "vip" ? "gold" : ""}`}>{t("pkg_save", { pct: save })}</span>
                </div>
                <div className="row spread mt-16" style={{ alignItems: "baseline" }}>
                  <span className="title2 tabular">
                    {money(p.price)} {t("sum")}
                  </span>
                  <span className="footnote secondary">{t("pkg_days", { days: p.days })}</span>
                </div>
                <div className="footnote secondary">
                  {t("per_one", { price: `${money(Math.round(p.price / p.count))} ${t("sum")}` })}
                  {p.notes_free && ` · ${t("pkg_notes")}`}
                  {p.priority && ` · ${t("pkg_priority")}`}
                </div>
                <div className="mt-16">
                  <Button kind={p.code === "month" ? "filled" : "tinted"} onClick={() => setBuying(p)}>
                    {t("buy")}
                  </Button>
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
        onPaid={() => {
          setToast(t("pay_pkg_ok"));
          setTimeout(() => qc.invalidateQueries({ queryKey: ["me"] }), 1500);
        }}
      />
      <Toast text={toast} onDone={() => setToast(null)} />
    </div>
  );
}
