import { useEffect, useRef, useState } from "react";

import { useT } from "../lib/app";
import { playPaid } from "../lib/sound";
import { haptic } from "../lib/tg";
import type { Package, SlideTier } from "../lib/types";
import { Coupon } from "./Coupon";
import { PackCard } from "./PackCard";

type Phase = "in" | "ok";

/**
 * Отмена оплаченного заказа — обратная анимация к оплате.
 * Из пакета: карта возвращается (если была разбита последней презентацией — осколки слетаются обратно).
 * Деньгами или пакет уже истёк: выезжает золотой купон на одну презентацию.
 */
export function ReturnOverlay({
  pkg,
  holder,
  cost,
  slides,
  onDone,
}: {
  pkg: Package | null; // null — купон
  holder: string;
  cost: number;
  slides: SlideTier;
  onDone: () => void;
}) {
  const t = useT();
  const mended = !!pkg && pkg.left <= cost; // до отмены карта была пустой — разбитой
  const [phase, setPhase] = useState<Phase>("in");
  const done = useRef(false);
  const finish = () => {
    if (done.current) return;
    done.current = true;
    onDone();
  };

  useEffect(() => {
    const timers = [
      setTimeout(
        () => {
          setPhase("ok");
          playPaid();
          haptic.success();
        },
        mended ? 1500 : 850,
      ),
      setTimeout(finish, mended ? 4200 : 3600),
    ];
    return () => timers.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  let body;
  if (!pkg) {
    body = <Coupon slides={slides} stamp />;
  } else {
    const card = <PackCard pkg={pkg} holder={holder} hint={false} still />;
    body = mended ? (
      <div className="shards">
        <div className="shard l">{card}</div>
        <div className="shard r">{card}</div>
      </div>
    ) : (
      card
    );
  }

  return (
    <div className={`paid-ov ret-ov ${phase}${mended ? " mended" : ""}${pkg ? "" : " is-coupon"}`} onClick={finish} role="status" aria-live="polite">
      <div className="paid-card">{body}</div>
      <div className="paid-mark">
        <svg viewBox="0 0 64 64" aria-hidden>
          <circle cx="32" cy="32" r="29" />
          <path d="M19 33.5l8.5 8.5L45 24" />
        </svg>
        <div className="paid-t">{t(pkg ? "ret_pack_t" : "ret_coupon_t")}</div>
        <div className="paid-s">{pkg ? t("ret_pack_s", { cost, left: pkg.left }) : t("ret_coupon_s")}</div>
      </div>
    </div>
  );
}
