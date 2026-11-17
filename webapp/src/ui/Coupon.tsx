import { Ticket } from "lucide-react";

import { useT } from "../lib/app";
import { slidesKey } from "../lib/order";
import type { SlideTier } from "../lib/types";

/** Золотой купон на одну презентацию: слева основная часть, справа отрывной корешок по пунктиру. */
export function Coupon({ slides, stamp = false, gift = false }: { slides: SlideTier; stamp?: boolean; gift?: boolean }) {
  const t = useT();
  return (
    <div className="coupon">
      <span className="coupon-shine" />
      <div className="coupon-main">
        <Ticket size={26} />
        <div>
          <b>{t("coupon_one")}</b>
          <small>{t(slidesKey(slides))}</small>
        </div>
      </div>
      <div className="coupon-stub">
        <span>{gift ? t("coupon_gift") : "SLIDELAB"}</span>
        {stamp && <i>{t("coupon_paid")}</i>}
      </div>
    </div>
  );
}
