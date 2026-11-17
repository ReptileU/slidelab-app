import { Ticket } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useMe, useT } from "../lib/app";

/** «У вас N оплаченная презентация» — после отмены оплаченного заказа. Нажатие — новый заказ. */
export function VoucherCard() {
  const t = useT();
  const nav = useNavigate();
  const n = useMe().data?.vouchers ?? 0;
  if (!n) return null;
  return (
    <button className="voucher-card" onClick={() => nav("/order")}>
      <Ticket size={26} />
      <span className="grow">
        <b>{n === 1 ? t("voucher_card_one") : t("voucher_card_many", { n })}</b>
        <small>{t("voucher_card_s")}</small>
      </span>
      <span className="voucher-go">{t("voucher_use")} ›</span>
    </button>
  );
}
