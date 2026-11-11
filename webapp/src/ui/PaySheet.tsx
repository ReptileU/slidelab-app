import { Check, Copy, CreditCard, ImagePlus, Star } from "lucide-react";
import { useRef, useState } from "react";

import { ApiError } from "../lib/api";
import { useCatalog, useT } from "../lib/app";
import { money } from "../lib/i18n";
import { alert, haptic, openInvoice } from "../lib/tg";
import type { Invoice } from "../lib/types";
import { Button, Cell, Group, Sheet } from ".";

/** Скопировать номер карты: clipboard API, а где его нет (старые WebView) — через скрытое поле. */
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      area.setSelectionRange(0, text.length);
      const ok = document.execCommand("copy");
      area.remove();
      return ok;
    } catch {
      return false;
    }
  }
}

/** Скриншот → JPEG до 1600 px: быстро отправляется и читается без потерь. */
async function shrink(file: File): Promise<string> {
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    const scale = Math.min(1, 1600 / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.naturalWidth * scale);
    canvas.height = Math.round(img.naturalHeight * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("canvas");
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.85);
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * Выбор способа оплаты. Звёзды — счёт Telegram, не выходя из приложения.
 * Перевод — тоже здесь: номера карт копируются касанием, скриншот оплаты уходит владельцу.
 */
export function PaySheet({
  open,
  title,
  amount,
  onClose,
  createInvoice,
  sendReceipt,
  onPaid,
  onReceipt,
}: {
  open: boolean;
  title: string;
  amount: number;
  onClose: () => void;
  createInvoice: (provider: "stars" | "card") => Promise<Invoice>;
  sendReceipt: (image: string) => Promise<unknown>;
  onPaid: () => void;
  onReceipt: () => void;
}) {
  const t = useT();
  const catalog = useCatalog();
  const [busy, setBusy] = useState(false);
  const [card, setCard] = useState<Invoice | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [shot, setShot] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const rate = catalog.data?.prices.uzs_per_star ?? 155;
  // Как to_stars на сервере: вверх до кратного 5, минимум 5 — иначе в счёте будет другая цифра
  const stars = Math.max(5, Math.ceil(amount / (rate * 5)) * 5);
  const starsOn = catalog.data?.stars ?? true;

  function close() {
    onClose();
    // даём шторке закрыться, потом сбрасываем шаг
    setTimeout(() => {
      setCard(null);
      setShot(null);
      setCopied(null);
    }, 300);
  }

  async function pay(provider: "stars" | "card") {
    if (busy) return;
    setBusy(true);
    try {
      const invoice = await createInvoice(provider);
      if (invoice.provider === "stars" && invoice.url) {
        onClose();
        const status = await openInvoice(invoice.url);
        if (status === "paid") {
          haptic.success();
          onPaid();
        }
      } else {
        setCard(invoice);
      }
    } catch (e) {
      haptic.error();
      await alert(e instanceof ApiError ? e.message : t("error"));
    } finally {
      setBusy(false);
    }
  }

  async function copy(number: string) {
    const digits = number.replace(/\s/g, "");
    if (await copyText(digits)) {
      haptic.success();
      setCopied(number);
      setTimeout(() => setCopied((c) => (c === number ? null : c)), 1800);
    } else {
      haptic.error();
    }
  }

  async function pick(file: File | undefined) {
    if (!file) return;
    try {
      setShot(await shrink(file));
      haptic.tap();
    } catch {
      haptic.error();
      await alert(t("pay_shot_bad"));
    }
  }

  async function send() {
    if (!shot || busy) return;
    setBusy(true);
    try {
      await sendReceipt(shot);
      haptic.success();
      close();
      onReceipt();
    } catch (e) {
      haptic.error();
      await alert(e instanceof ApiError ? e.message : t("error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open={open} onClose={close} title={card ? t("pay_card") : title}>
      <div className="center" style={{ marginBottom: 16 }}>
        <div className="title1 tabular">
          {money(amount)} {t("sum")}
        </div>
      </div>

      {!card ? (
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
      ) : (
        <>
          <div className="footnote secondary" style={{ margin: "0 4px 6px" }}>
            {t("pay_copy_hint")}
          </div>
          <Group icons>
            {card.cards.map((c) => (
              <Cell
                key={c.number}
                icon={<CreditCard />}
                title={<span className="tabular" style={{ whiteSpace: "nowrap" }}>{c.number}</span>}
                subtitle={copied === c.number ? t("pay_copied") : c.label}
                accessory={
                  copied === c.number ? (
                    <Check size={20} className="cell-check" />
                  ) : (
                    <Copy size={18} className="secondary" style={{ flex: "0 0 auto" }} />
                  )
                }
                onClick={() => copy(c.number)}
              />
            ))}
          </Group>
          {card.name && (
            <div className="footnote secondary" style={{ margin: "6px 4px 0" }}>
              {t("pay_holder", { name: card.name })}
            </div>
          )}

          <div className="footnote secondary" style={{ margin: "18px 4px 6px" }}>
            {t("pay_shot_hint")}
          </div>
          <input
            ref={picker}
            type="file"
            accept="image/*"
            hidden
            onChange={(e) => {
              void pick(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          {shot ? (
            <button className="pay-shot" onClick={() => picker.current?.click()} aria-label={t("pay_shot_change")}>
              <img src={shot} alt="" />
              <span>{t("pay_shot_change")}</span>
            </button>
          ) : (
            <Button kind="tinted" onClick={() => picker.current?.click()}>
              <ImagePlus size={18} /> {t("pay_shot")}
            </Button>
          )}
          <div className="mt-12">
            <Button disabled={!shot || busy} onClick={send}>
              {busy ? "…" : t("pay_shot_send")}
            </Button>
          </div>
        </>
      )}
    </Sheet>
  );
}
