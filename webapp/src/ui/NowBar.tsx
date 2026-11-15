import { ChevronRight, Presentation } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api";
import { useOrders, useT } from "../lib/app";
import { statusKey } from "../lib/order";
import { haptic } from "../lib/tg";
import type { OrderStatus } from "../lib/types";

/** Насколько заказ продвинулся — для полоски внизу плашки. */
const PROGRESS: Partial<Record<OrderStatus, number>> = {
  new: 0.18,
  cover: 0.4,
  awaiting_payment: 0.55,
  work: 0.78,
  revision: 0.9,
};
/** На этих этапах работаем мы — показываем «живые» полоски; на остальных ждём клиента — стрелка. */
const OURS: OrderStatus[] = ["new", "work", "revision"];

/**
 * Плашка над нижним меню, как мини-плеер: какой заказ сейчас готовится и на каком он этапе.
 * На вкладке «Заказы» её нет — там этот заказ и так первый в списке.
 */
export function NowBar() {
  const t = useT();
  const nav = useNavigate();
  const orders = useOrders();
  const order = orders.data?.find((o) => o.status in PROGRESS);
  const [thumb, setThumb] = useState<string | null>(null);

  useEffect(() => {
    setThumb(null);
    if (!order?.has_cover) return;
    let alive = true;
    api
      .thumbUrl(order.id)
      .then((url) => alive && setThumb(url))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [order?.id, order?.has_cover]);

  // Страницам нужен запас снизу, чтобы плашка не закрывала последний блок
  useEffect(() => {
    document.documentElement.classList.toggle("has-now", !!order);
    return () => document.documentElement.classList.remove("has-now");
  }, [!!order]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!order) return null;
  const ours = OURS.includes(order.status);
  return (
    <button
      className="now"
      onClick={() => {
        haptic.tap();
        nav(`/orders/${order.id}`);
      }}
    >
      <span className="now-art">{thumb ? <img src={thumb} alt="" /> : <Presentation size={20} strokeWidth={1.8} />}</span>
      <span className="now-text">
        <span className="now-title ellipsis">{order.topic}</span>
        <span className="now-stage ellipsis">
          {t("order_n", { id: order.id })} · {t(statusKey(order.status))}
        </span>
      </span>
      {ours ? (
        <span className="now-eq" aria-hidden>
          <i />
          <i />
          <i />
          <i />
        </span>
      ) : (
        <span className="now-go">
          <ChevronRight size={20} />
        </span>
      )}
      <span className="now-bar">
        <i style={{ width: `${(PROGRESS[order.status] ?? 0) * 100}%` }} />
      </span>
    </button>
  );
}
