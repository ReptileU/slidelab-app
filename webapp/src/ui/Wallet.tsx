import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import { useMe, useT } from "../lib/app";
import { shrink } from "../lib/image";
import { alert, haptic } from "../lib/tg";
import type { SlideTier } from "../lib/types";
import { Button, Cell, Group, Sheet } from ".";
import { Coupon } from "./Coupon";
import { PackCard } from "./PackCard";

type Item = { kind: "pack" } | { kind: "coupon"; slides: SlideTier };

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

  const coupons: Item[] = (me?.voucher_list ?? []).map((slides) => ({ kind: "coupon", slides }));
  const items: Item[] = [...coupons, ...(me?.package ? [{ kind: "pack" } as Item] : [])];
  const n = items.length;
  const photo = me?.wallet_cover ? cover.data : null;

  const render = (it: Item, still: boolean) =>
    it.kind === "pack" && me?.package ? (
      <PackCard pkg={me.package} holder={holder} hint={false} still={still} />
    ) : it.kind === "coupon" ? (
      <Coupon slides={it.slides} />
    ) : null;
  const sel = open !== null ? items[open] : null;

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

      <Sheet open={sel !== null} onClose={() => setOpen(null)} title={sel?.kind === "coupon" ? t("wallet_coupon_t") : t("pkg_my")}>
        {sel && <div className="wallet-sheet-card">{render(sel, false)}</div>}
        <p className="footnote secondary center" style={{ margin: "14px 8px 16px" }}>
          {sel?.kind === "coupon" ? t("voucher_kept_s") : t("wallet_pack_s")}
        </p>
        <Button
          onClick={() => {
            setOpen(null);
            nav(sel?.kind === "coupon" ? "/order" : "/packages");
          }}
        >
          {sel?.kind === "coupon" ? t("cta_order") : t("pkg_all")}
        </Button>
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
