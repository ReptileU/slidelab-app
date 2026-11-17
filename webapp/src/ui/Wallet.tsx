import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Gift as GiftIcon, ImagePlus, Minus, Plus } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import { useMe, useT } from "../lib/app";
import { shrink } from "../lib/image";
import { copyText } from "../lib/clipboard";
import { alert, confirm, haptic, openTelegramUrl } from "../lib/tg";
import { slidesKey } from "../lib/order";
import type { Gift, SlideTier } from "../lib/types";
import { Button, Cell, Group, Sheet, Toast } from ".";
import { Coupon } from "./Coupon";
import { PackCard } from "./PackCard";

type Item = { kind: "pack" } | { kind: "coupon"; id: number; slides: SlideTier; gift?: boolean };

const PEEK = 46; // сколько видно от каждой карты, торчащей из кошелька

/**
 * Кошелёк в профиле: из кармана торчат карта пакета и купоны. Касание — карта целиком.
 * Обложка — классическая кожа с инициалами SlideLab или фото клиента.
 */
export function Wallet() {
  const t = useT();
  const nav = useNavigate();
  const qc = useQueryClient();
  const me = useMe().data;
  const [open, setOpen] = useState<number | null>(null);
  const [skin, setSkin] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const holder = me?.first_name || "SlideLab";

  const cover = useQuery({
    queryKey: ["wallet-cover", me?.wallet_cover],
    queryFn: api.walletCoverUrl,
    enabled: !!me?.wallet_cover,
    staleTime: Infinity,
    retry: false,
  });
  const fail = (e: unknown) => {
    haptic.error();
    void alert(e instanceof ApiError ? e.message : t("error"));
  };
  const upload = useMutation({
    mutationFn: async (file: File) => api.setWalletCover(await shrink(file)),
    onSuccess: (m) => {
      haptic.success();
      qc.setQueryData(["me"], m);
      setSkin(false);
    },
    onError: fail,
  });
  const reset = useMutation({
    mutationFn: api.resetWalletCover,
    onSuccess: (m) => {
      haptic.select();
      qc.setQueryData(["me"], m);
      setSkin(false);
    },
    onError: fail,
  });

  const coupons: Item[] = (me?.coupons ?? []).map((c) => ({ kind: "coupon", id: c.id, slides: c.slides, gift: c.gift }));
  const items: Item[] = [...coupons, ...(me?.package ? [{ kind: "pack" } as Item] : [])];
  const n = items.length;
  const photo = me?.wallet_cover ? cover.data : null;

  const render = (it: Item, still: boolean) =>
    it.kind === "pack" && me?.package ? (
      <PackCard pkg={me.package} holder={holder} hint={false} still={still} />
    ) : it.kind === "coupon" ? (
      <Coupon slides={it.slides} gift={it.gift} />
    ) : null;
  const sel = open !== null ? items[open] : null;

  // Подарки: купон целиком или несколько презентаций из пакета — ссылкой другу
  const [step, setStep] = useState<"view" | "count" | "share">("view");
  const [count, setCount] = useState(1);
  const [made, setMade] = useState<Gift | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const sent = useQuery({ queryKey: ["gifts"], queryFn: api.gifts, staleTime: 30_000 });
  const closeItem = () => {
    setOpen(null);
    setTimeout(() => {
      setStep("view");
      setMade(null);
      setCount(1);
    }, 300);
  };
  const give = useMutation({
    mutationFn: () =>
      sel?.kind === "coupon" ? api.makeGift({ kind: "coupon", coupon_id: sel.id }) : api.makeGift({ kind: "pack", count }),
    onSuccess: (g) => {
      haptic.success();
      setMade(g);
      setStep("share");
      void qc.invalidateQueries({ queryKey: ["me"] });
      void qc.invalidateQueries({ queryKey: ["gifts"] });
    },
    onError: fail,
  });
  const revoke = useMutation({
    mutationFn: (id: number) => api.revokeGift(id),
    onSuccess: () => {
      haptic.success();
      setToast(t("gift_revoked"));
      void qc.invalidateQueries({ queryKey: ["me"] });
      void qc.invalidateQueries({ queryKey: ["gifts"] });
    },
    onError: fail,
  });
  const share = (g: Gift) =>
    openTelegramUrl(`https://t.me/share/url?url=${encodeURIComponent(g.link)}&text=${encodeURIComponent(t("gift_share_text"))}`);
  const copy = async (g: Gift) => {
    if (await copyText(g.link)) {
      haptic.success();
      setToast(t("gift_copied"));
    }
  };
  const giftTitle = (g: Gift) =>
    g.kind === "coupon" ? t("gift_row_coupon", { slides: g.slides ? t(slidesKey(g.slides)) : "" }) : t("gift_row_pack", { n: g.count });
  const left = me?.package?.left ?? 0;

  return (
    <>
      <div className={`wallet${n ? "" : " empty"}`} style={{ ["--n" as string]: n, ["--peek" as string]: `${PEEK}px` }}>
        <div className="wallet-back" />
        {items.map((it, i) => (
          <button
            key={i}
            className={`wallet-item ${it.kind}`}
            style={{ top: 18 + i * PEEK, zIndex: i + 1 }}
            onClick={() => {
              haptic.select();
              setOpen(i);
            }}
          >
            {render(it, true)}
          </button>
        ))}
        <div className={`wallet-front${photo ? " photo" : ""}`} style={photo ? { backgroundImage: `url(${photo})` } : undefined}>
          <span className="wallet-mono" aria-hidden>
            SL
          </span>
          <span className="wallet-brand">SLIDELAB</span>
          {!n && <span className="wallet-empty">{t("wallet_empty")}</span>}
          <button
            className="wallet-skin"
            onClick={() => {
              haptic.tap();
              setSkin(true);
            }}
            aria-label={t("wallet_skin")}
          >
            <ImagePlus size={16} />
          </button>
        </div>
      </div>

      {!!sent.data?.length && (
        <div className="gift-pending">
          <div className="footnote secondary gift-pending-t">{t("gift_pending_t")}</div>
          <Group>
            {sent.data.map((g) => (
              <Cell
                key={g.id}
                icon={<GiftIcon />}
                title={giftTitle(g)}
                subtitle={t("gift_pending_s")}
                value={
                  <span className="gift-acts">
                    <button onClick={() => share(g)}>{t("gift_send_short")}</button>
                    <button
                      className="danger"
                      disabled={revoke.isPending}
                      onClick={async () => {
                        if (await confirm(t("gift_revoke_q"))) revoke.mutate(g.id);
                      }}
                    >
                      {t("gift_revoke")}
                    </button>
                  </span>
                }
              />
            ))}
          </Group>
        </div>
      )}
      <Toast text={toast} onDone={() => setToast(null)} />

      <Sheet
        open={sel !== null}
        onClose={closeItem}
        title={step === "share" ? t("gift_ready_t") : sel?.kind === "coupon" ? t("wallet_coupon_t") : t("pkg_my")}
      >
        {step === "view" && sel && (
          <>
            <div className="wallet-sheet-card">{render(sel, false)}</div>
            <p className="footnote secondary center" style={{ margin: "14px 8px 16px" }}>
              {sel.kind === "coupon" ? t("voucher_kept_s") : t("wallet_pack_s")}
            </p>
            <Button
              onClick={() => {
                closeItem();
                nav(sel.kind === "coupon" ? "/order" : "/packages");
              }}
            >
              {sel.kind === "coupon" ? t("cta_order") : t("pkg_all")}
            </Button>
            {(sel.kind === "coupon" || left > 0) && (
              <div className="mt-12">
                <Button
                  kind="tinted"
                  disabled={give.isPending}
                  onClick={async () => {
                    haptic.tap();
                    if (sel.kind === "pack") setStep("count");
                    else if (await confirm(t("gift_coupon_q"))) give.mutate();
                  }}
                >
                  <GiftIcon size={18} /> {t("gift_btn")}
                </Button>
              </div>
            )}
          </>
        )}

        {step === "count" && (
          <>
            <p className="subhead secondary center" style={{ margin: "0 8px 18px" }}>
              {t("gift_count_s", { left })}
            </p>
            <div className="gift-count">
              <button aria-label="−" disabled={count <= 1} onClick={() => (haptic.select(), setCount((c) => Math.max(1, c - 1)))}>
                <Minus />
              </button>
              <b className="tabular">{count}</b>
              <button aria-label="+" disabled={count >= left} onClick={() => (haptic.select(), setCount((c) => Math.min(left, c + 1)))}>
                <Plus />
              </button>
            </div>
            <p className="footnote secondary center" style={{ margin: "12px 8px 18px" }}>
              {t("gift_count_after", { left: left - count })}
            </p>
            <Button disabled={give.isPending} onClick={() => give.mutate()}>
              <GiftIcon size={18} /> {t("gift_pack_btn", { n: count })}
            </Button>
          </>
        )}

        {step === "share" && made && (
          <>
            <div className="gift-ready">
              <GiftIcon size={44} />
              <b>{giftTitle(made)}</b>
              <span>{t("gift_ready_s")}</span>
            </div>
            <Button onClick={() => share(made)}>{t("gift_send_tg")}</Button>
            <div className="mt-12">
              <Button kind="tinted" onClick={() => void copy(made)}>
                {t("gift_copy")}
              </Button>
            </div>
            <p className="footnote secondary center" style={{ margin: "14px 8px 0" }}>
              {t("gift_can_revoke")}
            </p>
          </>
        )}
      </Sheet>

      <Sheet open={skin} onClose={() => setSkin(false)} title={t("wallet_skin")}>
        <Group>
          <Cell
            title={t("wallet_skin_classic")}
            subtitle={t("wallet_skin_classic_s")}
            checked={!me?.wallet_cover}
            onClick={() => me?.wallet_cover && reset.mutate()}
          />
          <Cell
            title={upload.isPending ? t("wallet_skin_loading") : t("wallet_skin_photo")}
            subtitle={t("wallet_skin_photo_s")}
            checked={!!me?.wallet_cover}
            chevron
            onClick={() => !upload.isPending && picker.current?.click()}
          />
        </Group>
        <input
          ref={picker}
          type="file"
          accept="image/*"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) upload.mutate(f);
          }}
        />
      </Sheet>
    </>
  );
}
