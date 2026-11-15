import { ChevronRight, Presentation } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api";
import { useOrders, useT } from "../lib/app";
import { statusKey } from "../lib/order";
import { haptic } from "../lib/tg";
import type { Order, OrderStatus } from "../lib/types";

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

/** Сначала заказы, где ждут клиента (обложка, оплата), потом остальные — свежие выше. */
function inProgress(orders: Order[] | undefined): Order[] {
  const waitsClient = (o: Order) => (OURS.includes(o.status) ? 1 : 0);
  return (orders ?? [])
    .filter((o) => o.status in PROGRESS)
    .sort((a, b) => waitsClient(a) - waitsClient(b) || b.id - a.id);
}

/**
 * Плашка над нижним меню, как мини-плеер: какие заказы сейчас готовятся и на каком они этапе.
 * Заказов несколько — плашка листается вбок, точки показывают, сколько их.
 * На вкладке «Заказы» её нет — там эти заказы и так первые в списке.
 */
export function NowBar() {
  const orders = useOrders();
  const list = inProgress(orders.data);
  const track = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);
  const count = list.length;

  // Страницам нужен запас снизу, чтобы плашка не закрывала последний блок
  useEffect(() => {
    document.documentElement.classList.toggle("has-now", count > 0);
    return () => document.documentElement.classList.remove("has-now");
  }, [count > 0]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!count) return null;
  const current = Math.min(index, count - 1);
  return (
    <div className="now-wrap">
      {count > 1 && (
        <div className="now-dots" aria-hidden>
          {list.map((o, i) => (
            <i key={o.id} className={i === current ? "on" : ""} />
          ))}
        </div>
      )}
      <div
        ref={track}
        className="now-track"
        onScroll={(e) => {
          const el = e.currentTarget;
          const next = Math.round(el.scrollLeft / el.clientWidth);
          if (next !== index) {
            setIndex(next);
            haptic.select();
          }
        }}
      >
        {list.map((o) => (
          <NowCard key={o.id} order={o} />
        ))}
      </div>
    </div>
  );
}

function NowCard({ order }: { order: Order }) {
  const t = useT();
  const nav = useNavigate();
  const [thumb, setThumb] = useState<string | null>(null);

  useEffect(() => {
    setThumb(null);
    if (!order.has_cover) return;
    let alive = true;
    api
      .thumbUrl(order.id)
      .then((url) => alive && setThumb(url))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [order.id, order.has_cover]);

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
