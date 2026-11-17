import { useEffect, useRef, useState } from "react";

import { useT } from "../lib/app";
import { playTear } from "../lib/sound";
import { haptic, tg } from "../lib/tg";
import type { SlideTier } from "../lib/types";
import { Coupon } from "./Coupon";

type Phase = "in" | "tug" | "torn";

/**
 * Заказ оплачен купоном: купон выезжает, его тянут — и он рвётся по пунктиру с дырочками,
 * корешок улетает вниз. Звук рвущейся бумаги и дробная вибрация, без «звона» оплаты картой.
 */
export function CouponTear({ slides, onDone }: { slides: SlideTier; onDone: () => void }) {
  const t = useT();
  const [phase, setPhase] = useState<Phase>("in");
  const done = useRef(false);
  const finish = () => {
    if (done.current) return;
    done.current = true;
    onDone();
  };

  useEffect(() => {
    const buzz = (style: "light" | "medium" | "rigid") => {
      try {
        tg?.HapticFeedback.impactOccurred(style);
      } catch {
        /* без вибрации */
      }
    };
    const timers = [
      setTimeout(() => setPhase("tug"), 800),
      setTimeout(() => {
        setPhase("torn");
        playTear();
        // дробь по волокнам, затем отрыв
        [0, 70, 140, 210, 280].forEach((d, i) => timers.push(setTimeout(() => buzz(i < 4 ? "light" : "rigid"), d)));
      }, 1250),
      setTimeout(() => haptic.success(), 1750),
      setTimeout(finish, 3600),
    ];
    return () => timers.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const coupon = <Coupon slides={slides} />;
  return (
    <div className={`paid-ov tear-ov ${phase}`} onClick={finish} role="status" aria-live="polite">
      <div className="paid-card">
        <div className="tear">
          <div className="tear-half l">{coupon}</div>
          <div className="tear-half r">{coupon}</div>
        </div>
      </div>
      <div className="paid-mark">
        <div className="paid-t">{t("tear_t")}</div>
        <div className="paid-s">{t("tear_s")}</div>
      </div>
    </div>
  );
}
