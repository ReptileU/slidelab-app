import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../lib/api";
import { useT } from "../lib/app";
import { haptic } from "../lib/tg";
import { CaseArt, CaseSheet } from "./PointsCase";

const SHOWN = "sl_welcome_shown"; // приветственный кейс уже показывали сам — второй раз не навязываем

/**
 * Для того, кто пришёл по ссылке друга. Пока не открыт приветственный кейс — плашка «Подарок от друга»
 * (и при первом входе кейс открывается сам). После — напоминание про двойные баллы за первую покупку.
 */
export function FriendGift() {
  const t = useT();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const q = useQuery({ queryKey: ["referrals"], queryFn: api.referrals, staleTime: 60_000 });
  const [open, setOpen] = useState(false);
  const welcome = q.data?.welcome ?? null;

  useEffect(() => {
    if (!welcome) return;
    let shown = false;
    try {
      shown = localStorage.getItem(SHOWN) === "1";
      localStorage.setItem(SHOWN, "1");
    } catch {
      /* без памяти браузера — откроем по кнопке из бота */
    }
    if (params.get("welcome") === "1" || !shown) setOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [!!welcome]);

  if (!q.data) return null;
  if (welcome)
    return (
      <>
        <button
          className="fgift welcome"
          onClick={() => {
            haptic.tap();
            setOpen(true);
          }}
        >
          <CaseArt tier="welcome" size={84} />
          <span className="fgift-t">
            <b>{t("welcome_t")}</b>
            <span>{t("welcome_s")}</span>
          </span>
        </button>
        {open && (
          <CaseSheet
            box={welcome}
            points={0}
            onOpen={() => api.openWelcome()}
            onClose={(opened) => {
              setOpen(false);
              if (opened) {
                void qc.invalidateQueries({ queryKey: ["referrals"] });
                void qc.invalidateQueries({ queryKey: ["me"] });
              }
            }}
          />
        )}
      </>
    );
  if (!q.data.invited) return null;
  return (
    <button className="fgift" onClick={() => nav("/cover")}>
      <CaseArt tier="small" size={84} />
      <span className="fgift-t">
        <b>{t("ref_gift_t")}</b>
        <span>{t("ref_gift_s", { n: q.data.friend_points })}</span>
      </span>
    </button>
  );
}
