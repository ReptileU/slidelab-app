import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useMe } from "../lib/app";
import { unlockAudio } from "../lib/sound";
import { haptic } from "../lib/tg";
import type { BoxPrize, LuckyPrize, Package, PlanCode, PointsBox, PointsBoxKey, PointsInfo } from "../lib/types";
import { Button, Section, Segmented } from "../ui";
import { DiscountCard } from "../ui/Discount";
import { LuckyReveal, type Rarity } from "../ui/LuckyPack";
import { CaseSheet } from "../ui/PointsCase";
import { DEMO as FLY_DEMO } from "../ui/PointsFly";
import { PointsShop } from "../ui/PointsShop";
import { PackCard } from "../ui/PackCard";
import { CouponTear } from "../ui/CouponTear";
import { PaidOverlay } from "../ui/PaidOverlay";
import { ReturnOverlay } from "../ui/ReturnOverlay";
import { BackButton } from "../ui/TelegramButtons";

const PLANS: Record<string, { total: number }> = { week: { total: 2 }, month: { total: 4 }, vip: { total: 10 } };

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
      { prize: "discount", value: 30, percent: 20 }, { prize: "discount", value: 50, percent: 20 },
      { prize: "one", value: 1, percent: 30 }, { prize: "two", value: 2, percent: 25 }, { prize: "four", value: 4, percent: 5 } ] },
    { key: "large", price: 500, prizes: [
      { prize: "discount", value: 50, percent: 25 }, { prize: "one", value: 1, percent: 7 },
      { prize: "two", value: 2, percent: 25 }, { prize: "four", value: 4, percent: 40 }, { prize: "vip", value: 10, percent: 3 } ] },
  ],
};
/** Приветственный кейс — как на сервере (points.WELCOME). */
const WELCOME_DEMO: PointsBox = {
  key: "welcome",
  price: 0,
  prizes: [
    { prize: "one", value: 1, percent: 15 },
    { prize: "discount", value: 30, percent: 40 },
    { prize: "discount", value: 20, percent: 45 },
  ],
};

/** Призы кейсов — по одному каждого вида, с той редкостью, с какой они выпадают в кейсах. */
const DEMO_DROPS: { label: string; prize: BoxPrize; value: number; rarity: Rarity }[] = [
  { label: "Скидка 20% — обычный", prize: "discount", value: 20, rarity: "common" },
  { label: "1 купон — редкий", prize: "one", value: 1, rarity: "rare" },
  { label: "+60 баллов — эпический", prize: "points", value: 60, rarity: "epic" },
  { label: "Пакет на 2 — редкий", prize: "two", value: 2, rarity: "rare" },
  { label: "Пакет на 4 — эпический", prize: "four", value: 4, rarity: "epic" },
  { label: "VIP на 10 — легендарный", prize: "vip", value: 10, rarity: "legend" },
];

/** Демо эффектов пакета для владельца (/demo в боте): ничего не заказывается и не списывается. */
export function Demo() {
  const nav = useNavigate();
  const me = useMe();
  const [plan, setPlan] = useState<PlanCode>("month");
  const [demoCase, setDemoCase] = useState<PointsBoxKey | null>(null);
  const [welcome, setWelcome] = useState(false);
  const [show, setShow] = useState<null | "paid" | "last">(null);
  const [coupon, setCoupon] = useState<null | "tear" | "back" | "mend">(null);
  const play = (k: "tear" | "back" | "mend") => {
    haptic.tap();
    unlockAudio();
    setCoupon(k);
  };
  const [box, setBox] = useState<(LuckyPrize & { rarity: Rarity }) | null>(null);
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
      <Section title="Баллы и кейсы за баллы">
        <PointsShop info={POINTS_DEMO} onSelect={(k) => setDemoCase(k)} />
      </Section>
      {demoCase && (
        <CaseSheet
          box={POINTS_DEMO.boxes.find((b) => b.key === demoCase)!}
          points={POINTS_DEMO.points}
          onOpen={async () => {
            const box = POINTS_DEMO.boxes.find((b) => b.key === demoCase)!;
            let r = Math.random() * 100;
            const p = box.prizes.find((x) => (r -= x.percent) <= 0) ?? box.prizes[0]!;
            return { prize: p.prize, value: p.value, points: POINTS_DEMO.points - box.price };
          }}
          onClose={() => setDemoCase(null)}
        />
      )}
      <Section title="Новичок по ссылке друга" footer="Так приветственный кейс видит человек, который впервые пришёл по приглашению.">
        <Button kind="tinted" onClick={() => setWelcome(true)}>
          Подарок от друга — приветственный кейс
        </Button>
      </Section>
      {welcome && (
        <CaseSheet
          box={WELCOME_DEMO}
          points={0}
          onOpen={async () => {
            let r = Math.random() * 100;
            const p = WELCOME_DEMO.prizes.find((x) => (r -= x.percent) <= 0) ?? WELCOME_DEMO.prizes[0]!;
            return { prize: p.prize, value: p.value, points: 0 };
          }}
          onClose={() => setWelcome(false)}
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
      <Section title="Выпадение призов" footer="Чем реже приз, тем громче выпадение: обычный, редкий, эпический, легендарный.">
        <div className="stack gap-12">
          {DEMO_DROPS.map((d) => (
            <Button
              key={d.label}
              kind="tinted"
              onClick={() => {
                haptic.tap();
                unlockAudio();
                setBox({ prize: d.prize, count: d.value, rarity: d.rarity });
              }}
            >
              {d.label}
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
      {box && (
        <LuckyReveal
          key={`${box.prize}${box.count}`}
          opened
          rarity={box.rarity}
          prize={box}
          name="Демо-кейс"
          onDone={() => setBox(null)}
        />
      )}
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
