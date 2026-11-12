import { useEffect, useRef, useState } from "react";

import { useT } from "../lib/app";
import { playPaid } from "../lib/sound";
import { haptic } from "../lib/tg";
import type { Package } from "../lib/types";
import { PackCard } from "./PackCard";

/**
 * Оплата из пакета: карта выезжает снизу, на ней уже новый остаток, затем — галочка «Оплачено» со звуком и вибрацией.
 * Через пару секунд (или по касанию) — дальше, на экран заказа.
 */
export function PaidOverlay({
  pkg,
  holder,
  cost,
  onDone,
}: {
  pkg: Package;
  holder: string;
  cost: number;
  onDone: () => void;
}) {
  const t = useT();
  const [phase, setPhase] = useState<"in" | "paid">("in");
  const done = useRef(false);
  const finish = () => {
    if (done.current) return;
    done.current = true;
    onDone();
  };

  useEffect(() => {
    const a = setTimeout(() => {
      setPhase("paid");
      playPaid();
      haptic.success();
    }, 750);
    const b = setTimeout(finish, 2900);
    return () => {
      clearTimeout(a);
      clearTimeout(b);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className={`paid-ov ${phase}`} onClick={finish} role="status" aria-live="polite">
      <div className="paid-card">
        <PackCard pkg={pkg} holder={holder} hint={false} />
      </div>
      <div className="paid-mark">
        <svg viewBox="0 0 64 64" aria-hidden>
          <circle cx="32" cy="32" r="29" />
          <path d="M19 33.5l8.5 8.5L45 24" />
        </svg>
        <div className="paid-t">{t("paid_done")}</div>
        <div className="paid-s">{t("paid_from_pkg", { cost, left: pkg.left })}</div>
      </div>
    </div>
  );
}
