import { CreditCard, Star } from "lucide-react";
import { useState } from "react";

import { ApiError } from "../lib/api";
import { useCatalog, useT } from "../lib/app";
import { money } from "../lib/i18n";
import { alert, haptic, openChat, openInvoice } from "../lib/tg";
import type { Invoice } from "../lib/types";
import { Cell, Group, Sheet } from ".";

/** Выбор способа оплаты: звёзды — не выходя из приложения, перевод — реквизиты и чек в чате. */
export function PaySheet({
  open,
  title,
  amount,
  onClose,
  createInvoice,
  onPaid,
}: {
  open: boolean;
  title: string;
  amount: number;
  onClose: () => void;
  createInvoice: (provider: "stars" | "card") => Promise<Invoice>;
  onPaid: () => void;
}) {
  const t = useT();
  const catalog = useCatalog();
  const [busy, setBusy] = useState(false);
  const rate = catalog.data?.prices.uzs_per_star ?? 155;
  // Как to_stars на сервере: вверх до кратного 5, минимум 5 — иначе в счёте будет другая цифра
  const stars = Math.max(5, Math.ceil(amount / (rate * 5)) * 5);
  const starsOn = catalog.data?.stars ?? true;

  async function pay(provider: "stars" | "card") {
    if (busy) return;
    setBusy(true);
    try {
      const invoice = await createInvoice(provider);
      onClose();
      if (invoice.provider === "stars" && invoice.url) {
        const status = await openInvoice(invoice.url);
        if (status === "paid") {
          haptic.success();
          onPaid();
        }
      } else {
        await alert(t("pay_card_sent"));
        openChat(catalog.data?.bot_username ?? "slidelab_order_bot");
      }
    } catch (e) {
      haptic.error();
      await alert(e instanceof ApiError ? e.message : t("error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open={open} onClose={onClose} title={title}>
      <div className="center" style={{ marginBottom: 16 }}>
        <div className="title1 tabular">
          {money(amount)} {t("sum")}
        </div>
      </div>
      <Group icons>
        {starsOn && (
          <Cell
            icon={<Star fill="currentColor" />}
            title={t("pay_stars")}
            subtitle={t("pay_stars_x", { stars })}
            chevron
            disabled={busy}
            onClick={() => pay("stars")}
          />
        )}
        <Cell
          icon={<CreditCard />}
          title={t("pay_card")}
          subtitle={t("pay_card_x")}
          chevron
          disabled={busy}
          onClick={() => pay("card")}
        />
      </Group>
    </Sheet>
  );
}
