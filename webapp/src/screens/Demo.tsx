import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useMe } from "../lib/app";
import { unlockAudio } from "../lib/sound";
import { haptic } from "../lib/tg";
import type { Package, PlanCode } from "../lib/types";
import { Button, Section, Segmented } from "../ui";
import { PackCard } from "../ui/PackCard";
import { PaidOverlay } from "../ui/PaidOverlay";
import { BackButton } from "../ui/TelegramButtons";

const PLANS: Record<string, { total: number }> = { week: { total: 2 }, month: { total: 4 }, vip: { total: 10 } };

/** Демо эффектов пакета для владельца (/demo в боте): ничего не заказывается и не списывается. */
export function Demo() {
  const nav = useNavigate();
  const me = useMe();
  const [plan, setPlan] = useState<PlanCode>("month");
  const [show, setShow] = useState<null | "paid" | "last">(null);
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
