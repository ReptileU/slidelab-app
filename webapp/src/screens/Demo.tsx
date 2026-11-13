import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useMe } from "../lib/app";
import { unlockAudio } from "../lib/sound";
import { haptic } from "../lib/tg";
import type { BoxPrize, LuckyInfo, LuckyPrize, Package, PlanCode } from "../lib/types";
import { Button, Section, Segmented } from "../ui";
import { LuckyCard, LuckyReveal } from "../ui/LuckyPack";
import { PackCard } from "../ui/PackCard";
import { PaidOverlay } from "../ui/PaidOverlay";
import { BackButton } from "../ui/TelegramButtons";

const PLANS: Record<string, { total: number }> = { week: { total: 2 }, month: { total: 4 }, vip: { total: 10 } };

const PRIZES: Record<BoxPrize, number> = { one: 1, two: 2, four: 4, vip: 10 };
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
  const [show, setShow] = useState<null | "paid" | "last">(null);
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
