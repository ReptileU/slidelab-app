import { Plus, Presentation } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useLang, useOrders, useT } from "../lib/app";
import { formatDate } from "../lib/i18n";
import { STATUS_BADGE, statusKey } from "../lib/order";
import { Button, Cell, Empty, Group, Section, Skeleton } from "../ui";

export function Orders() {
  const t = useT();
  const { lang } = useLang();
  const nav = useNavigate();
  const orders = useOrders();
  const list = orders.data ?? [];
  const active = list.filter((o) => !["done", "cancelled"].includes(o.status));
  const past = list.filter((o) => ["done", "cancelled"].includes(o.status));

  return (
    <div className="page">
      <div className="row spread" style={{ margin: "8px 0 20px" }}>
        <h1 className="large-title">{t("orders_t")}</h1>
        {list.length > 0 && (
          <button className="btn btn-tinted btn-small" onClick={() => nav("/order")} aria-label={t("new_order")}>
            <Plus size={18} strokeWidth={2.5} />
          </button>
        )}
      </div>

      {orders.isLoading && <Skeleton height={140} />}

      {orders.isSuccess && list.length === 0 && (
        <Empty
          icon={<Presentation />}
          title={t("orders_empty")}
          text={t("orders_empty_x")}
          action={<Button onClick={() => nav("/order")}>{t("new_order")}</Button>}
        />
      )}

      {[active, past].map(
        (group, i) =>
          group.length > 0 && (
            <Section key={i}>
              <Group>
                {group.map((o) => (
                  <Cell
                    key={o.id}
                    title={<span className="ellipsis" style={{ display: "block" }}>{o.topic}</span>}
                    subtitle={`#${o.id} · ${formatDate(o.created_at, lang)}`}
                    accessory={<span className={`badge ${STATUS_BADGE[o.status]}`}>{t(statusKey(o.status))}</span>}
                    chevron
                    onClick={() => nav(`/orders/${o.id}`)}
                  />
                ))}
              </Group>
            </Section>
          ),
      )}
    </div>
  );
}
