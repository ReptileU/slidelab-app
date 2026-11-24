import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useMe } from "../lib/app";
import { unlockAudio } from "../lib/sound";
import { haptic } from "../lib/tg";
import type { BoxPrize, LuckyInfo, LuckyPrize, Package, PlanCode, PointsBoxKey, PointsInfo } from "../lib/types";
import { Button, Section, Segmented } from "../ui";
import { DiscountCard } from "../ui/Discount";
import { LuckyCard, LuckyReveal } from "../ui/LuckyPack";
import { CaseSheet } from "../ui/PointsCase";
import { DEMO as FLY_DEMO } from "../ui/PointsFly";
import { PointsShop } from "../ui/PointsShop";
import { PackCard } from "../ui/PackCard";
import { CouponTear } from "../ui/CouponTear";
import { PaidOverlay } from "../ui/PaidOverlay";
import { ReturnOverlay } from "../ui/ReturnOverlay";
import { BackButton } from "../ui/TelegramButtons";

const PLANS: Record<string, { total: number }> = { week: { total: 2 }, month: { total: 4 }, vip: { total: 10 } };

const PRIZES: Record<BoxPrize, number> = { one: 1, two: 2, four: 4, vip: 10, coupons: 3, discount: 30, points: 60 };

/** Те же пакеты за баллы, что на сервере (services/points.py) — только для показа. */
const POINTS_DEMO: PointsInfo = {
  points: 260,
  expire_at: new Date(Date.now() + 170 * 864e5).toISOString(),
  per_presentation: 50,
  expire_days: 180,
  discount_pct: null,
  boxes: [
    { key: "small", price: 100, prizes: [
      { prize: "discount", value: 20, percent: 45 }, { prize: "discount", value: 30, percent: 25 },
      { prize: "one", value: 1, percent: 15 }, { prize: "points", value: 60, percent: 10 }, { prize: "two", value: 2, percent: 5 } ] },
    { key: "medium", price: 250, prizes: [
      { prize: "discount", value: 30, percent: 30 }, { prize: "discount", value: 50, percent: 25 },
      { prize: "coupons", value: 2, percent: 25 }, { prize: "two", value: 2, percent: 15 }, { prize: "coupons", value: 3, percent: 5 } ] },
    { key: "large", price: 500, prizes: [
      { prize: "discount", value: 50, percent: 35 }, { prize: "coupons", value: 3, percent: 20 },
      { prize: "four", value: 4, percent: 25 }, { prize: "coupons", value: 5, percent: 15 }, { prize: "coupons", value: 6, percent: 5 } ] },
  ],
};
/** Те же шансы, что на сервере (services/lucky.py) — здесь только для показа карточки. */
const LUCKY_DEMO: LuckyInfo = {
  price: 17000,
  odds: [
    { prize: "one", count: 1, percent: 88 },
    { prize: "two", count: 2, percent: 9 },
    { prize: "four", count: 4, percent: 2.5 },
    { prize: "vip", count: 10, percent: 0.5 },
  ],
  limit: 2,
  window_days: 7,
  can_buy: true,
  pending: null,
};

/** Демо эффектов пакета для владельца (/demo в боте): ничего не заказывается и не списывается. */
export function Demo() {
  const nav = useNavigate();
  const me = useMe();
  const [plan, setPlan] = useState<PlanCode>("month");
  const [demoCase, setDemoCase] = useState<PointsBoxKey | null>(null);
  const [show, setShow] = useState<null | "paid" | "last">(null);
  const [coupon, setCoupon] = useState<null | "tear" | "back" | "mend">(null);
  const play = (k: "tear" | "back" | "mend") => {
    haptic.tap();
    unlockAudio();
    setCoupon(k);
  };
  const [prize, setPrize] = useState<BoxPrize>("one");
  const [box, setBox] = useState<LuckyPrize | null>(null);
  const openDemo = () => {
    haptic.tap();
    unlockAudio();
    setBox({ prize, count: PRIZES[prize] });
  };
  const total = PLANS[plan]?.total ?? 4;
  const expires = new Date(Date.now() + 14 * 864e5).toISOString();
  const pkg: Package = { plan, left: Math.max(1, total - 1), total, expires_at: expires };
  const holder = me.data?.first_name || "SlideLab";

  return (
    <div className="page no-tabbar">
      <BackButton onClick={() => nav("/", { replace: true })} />
      <h1 className="large-title" style={{ margin: "8px 0 8px" }}>
        Демо
      </h1>
      <p className="subhead secondary" style={{ margin: "0 0 20px" }}>
        Только посмотреть: заказы не создаются, ничего не списывается.
      </p>
      <Section>
        <Segmented
          value={plan}
          onChange={setPlan}
          options={[
            { value: "week" as PlanCode, label: "2" },
            { value: "month", label: "4" },
            { value: "vip", label: "VIP" },
          ]}
        />
      </Section>
      <Section title="Карта на главной">
        <PackCard key={plan} pkg={pkg} holder={holder} />
      </Section>
      <Section>
        <div className="stack gap-12">
          <Button
            onClick={() => {
              haptic.tap();
              unlockAudio();
              setShow("paid");
            }}
          >
            Заказ из пакета — «Оплачено»
          </Button>
          <Button
            kind="tinted"
            onClick={() => {
              haptic.tap();
              unlockAudio();
              setShow("last");
            }}
          >
            Последняя — карта ломается
          </Button>
        </div>
      </Section>
      <Section title="Купон и отмена" footer="Купон появляется, когда клиент отменил оплаченный заказ.">
        <div className="stack gap-12">
          <Button onClick={() => play("tear")}>Оплата купоном — купон рвётся</Button>
          <Button kind="tinted" onClick={() => play("back")}>
            Отмена — выезжает купон
          </Button>
          <Button kind="tinted" onClick={() => play("mend")}>
            Отмена последней из пакета — карта собирается
          </Button>
        </div>
      </Section>
      <Section title="Бонус-пакет">
        <LuckyCard info={LUCKY_DEMO} preview onBuy={openDemo} onOpen={openDemo} />
      </Section>
      <Section title="Что выпадет в демо">
        <Segmented
          value={prize}
          onChange={setPrize}
          options={[
            { value: "one" as BoxPrize, label: "1" },
            { value: "two", label: "2" },
            { value: "four", label: "4" },
            { value: "vip", label: "VIP" },
          ]}
        />
        <div className="mt-16">
          <Button onClick={openDemo}>Открыть бонус-пакет</Button>
        </div>
      </Section>
      <Section title="Баллы и кейсы за баллы">
        <PointsShop info={POINTS_DEMO} onSelect={(k) => setDemoCase(k)} />
      </Section>
      {demoCase && (
        <CaseSheet
          box={POINTS_DEMO.boxes.find((b) => b.key === demoCase)!}
          points={POINTS_DEMO.points}
          onOpen={async () => {
            const box = POINTS_DEMO.boxes.find((b) => b.key === demoCase)!;
            const p = box.prizes[Math.floor(Math.random() * box.prizes.length)]!;
            return { prize: p.prize, value: p.value, points: POINTS_DEMO.points - box.price };
          }}
          onClose={() => setDemoCase(null)}
        />
      )}
      <Section title="Баллы после оплаты">
        <Button
          kind="tinted"
          onClick={() => {
            try {
              sessionStorage.setItem(FLY_DEMO, "50");
            } catch {
              /* ignore */
            }
            nav("/");
          }}
        >
          Полёт баллов во вкладку «Пакеты»
        </Button>
      </Section>
      <Section title="Карта скидки">
        <DiscountCard pct={30} holder={holder} />
        <div className="mt-16">
          <DiscountCard pct={50} holder={holder} />
        </div>
      </Section>
      <Section title="Призы за баллы">
        <div className="stack gap-12">
          {(["coupons", "discount", "points"] as BoxPrize[]).map((p) => (
            <Button
              key={p}
              kind="tinted"
              onClick={() => {
                haptic.tap();
                unlockAudio();
                setBox({ prize: p, count: PRIZES[p] });
              }}
            >
              {p === "coupons" ? "3 купона" : p === "discount" ? "Скидка 30%" : "+60 баллов"}
            </Button>
          ))}
        </div>
      </Section>
      {coupon === "tear" && <CouponTear slides="s20" onDone={() => setCoupon(null)} />}
      {(coupon === "back" || coupon === "mend") && (
        <ReturnOverlay
          key={coupon}
          pkg={coupon === "mend" ? { ...pkg, left: 1 } : null}
          holder={holder}
          cost={1}
          slides="s20"
          onDone={() => setCoupon(null)}
        />
      )}
      {box && <LuckyReveal key={box.prize} prize={box} onDone={() => setBox(null)} />}
      {show && (
        <PaidOverlay
          key={show + plan}
          pkg={{ ...pkg, left: show === "last" ? 0 : pkg.left - 1 }}
          holder={holder}
          cost={1}
          onDone={() => setShow(null)}
          onBuy={() => setShow(null)}
        />
      )}
    </div>
  );
}
