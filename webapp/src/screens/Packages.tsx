import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, ApiError } from "../lib/api";
import { useCatalog, useLang, useMe, useT } from "../lib/app";
import { money, type Key } from "../lib/i18n";
import { alert, haptic } from "../lib/tg";
import type { BuyPlan, LuckyPrize } from "../lib/types";
import { presWord } from "../lib/words";
import { Section, Skeleton, Toast } from "../ui";
import { LuckyCard, LuckyReveal } from "../ui/LuckyPack";
import { PackCard } from "../ui/PackCard";
import { PaySheet } from "../ui/PaySheet";

/** Картинка-фон пакета: чем дороже пакет, тем статуснее (серебро → платина → золото). */
const PACK_ART: Record<string, string> = { week: "p0", month: "p1b", vip: "p2" };

export function Packages() {
  const t = useT();
  const { lang } = useLang();
  const qc = useQueryClient();
  const me = useMe();
  const catalog = useCatalog();
  const [buying, setBuying] = useState<{ code: BuyPlan; price: number } | null>(null);
  const [reveal, setReveal] = useState<LuckyPrize | null>(null);
  const [waitBox, setWaitBox] = useState(false); // звёзды оплачены — ждём, пока сервер начислит бонус-пакет
  const lucky = useQuery({ queryKey: ["lucky"], queryFn: api.lucky, retry: false, refetchInterval: waitBox ? 1500 : false });

  async function openBox() {
    try {
      haptic.tap();
      setReveal(await api.luckyOpen());
    } catch (e) {
      await alert(e instanceof ApiError ? e.message : t("error"));
    }
  }

  // Оплатили звёздами — пакет появится через секунду-другую: открываем его сразу
  useEffect(() => {
    if (waitBox && lucky.data?.pending) {
      setWaitBox(false);
      void openBox();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waitBox, lucky.data?.pending]);

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
          <PackCard pkg={pkg} holder={me.data?.first_name || "SlideLab"} />
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

      {lucky.data && (
        <Section title={t("lucky_section")} footer={t("lucky_section_x")}>
          <LuckyCard
            info={lucky.data}
            onBuy={() => setBuying({ code: "lucky", price: lucky.data.price })}
            onOpen={() => void openBox()}
          />
        </Section>
      )}

      <PaySheet
        open={!!buying}
        title={buying ? planName(buying.code) : ""}
        amount={buying?.price ?? 0}
        onClose={() => setBuying(null)}
        createInvoice={(provider) => api.packageInvoice(buying!.code, provider)}
        sendReceipt={(image) => api.packageReceipt(buying!.code, image)}
        onReceipt={() => setToast(t("pay_shot_sent"))}
        onPaid={() => {
          if (buying?.code === "lucky") setWaitBox(true);
          else setToast(t("pay_pkg_ok"));
          setTimeout(() => qc.invalidateQueries({ queryKey: ["me"] }), 1500);
        }}
      />
      {reveal && (
        <LuckyReveal
          prize={reveal}
          onDone={() => {
            setReveal(null);
            void qc.invalidateQueries({ queryKey: ["lucky"] });
            void qc.invalidateQueries({ queryKey: ["me"] });
          }}
        />
      )}
      <Toast text={toast} onDone={() => setToast(null)} />
    </div>
  );
}
