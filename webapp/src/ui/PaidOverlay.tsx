import { useEffect, useRef, useState } from "react";

import { useT } from "../lib/app";
import { playCrack, playPaid } from "../lib/sound";
import { haptic, tg } from "../lib/tg";
import type { Package } from "../lib/types";
import { PackCard } from "./PackCard";

type Phase = "in" | "paid" | "broken";

/**
 * Оплата из пакета: карта выезжает снизу с новым остатком, затем галочка «Оплачено» со звуком и вибрацией.
 * Если это была последняя презентация — после галочки карта трескается и разлетается, и предлагаем купить новый пакет.
 */
export function PaidOverlay({
  pkg,
  holder,
  cost,
  onDone,
  onBuy,
}: {
  pkg: Package;
  holder: string;
  cost: number;
  onDone: () => void;
  onBuy: () => void;
}) {
  const t = useT();
  const last = pkg.left <= 0;
  const [phase, setPhase] = useState<Phase>("in");
  const done = useRef(false);
  const finish = (go: () => void) => {
    if (done.current) return;
    done.current = true;
    go();
  };

  useEffect(() => {
    const timers = [
      setTimeout(() => {
        setPhase("paid");
        playPaid();
        haptic.success();
      }, 750),
    ];
    if (last) {
      timers.push(
        setTimeout(() => {
          setPhase("broken");
          playCrack();
          try {
            tg?.HapticFeedback.impactOccurred("heavy");
          } catch {
            /* без вибрации */
          }
        }, 2300),
      );
    } else {
      timers.push(setTimeout(() => finish(onDone), 2900));
    }
    return () => timers.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const card = <PackCard pkg={pkg} holder={holder} hint={false} still />;

  return (
    <div
      className={`paid-ov ${phase}${last ? " last" : ""}`}
      onClick={() => !last && finish(onDone)}
      role="status"
      aria-live="polite"
    >
      <div className="paid-card">
        {last ? (
          <div className="shards">
            <div className="shard l">{card}</div>
            <div className="shard r">{card}</div>
            <svg className="crack" viewBox="0 0 100 63" preserveAspectRatio="none" aria-hidden>
              <polyline points="52,0 47,14 55,26 46,40 53,51 49,63" />
            </svg>
          </div>
        ) : (
          card
        )}
      </div>

      {phase !== "broken" ? (
        <div className="paid-mark">
          <svg viewBox="0 0 64 64" aria-hidden>
            <circle cx="32" cy="32" r="29" />
            <path d="M19 33.5l8.5 8.5L45 24" />
          </svg>
          <div className="paid-t">{t("paid_done")}</div>
          <div className="paid-s">{t("paid_from_pkg", { cost, left: pkg.left })}</div>
        </div>
      ) : (
        <div className="pkg-over">
          <div className="paid-t">{t("pkg_over_t")}</div>
          <div className="paid-s">{t("pkg_over_s")}</div>
          <button className="pack-buy gold-btn" onClick={() => finish(onBuy)}>
            {t("pkg_over_buy")}
          </button>
          <button className="pkg-over-later" onClick={() => finish(onDone)}>
            {t("pkg_over_later")}
          </button>
        </div>
      )}
    </div>
  );
}
