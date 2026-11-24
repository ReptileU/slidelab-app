import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api";
import { useT } from "../lib/app";
import { CaseArt } from "./PointsCase";

/** Плашка на главной для того, кто пришёл по ссылке друга и ещё не покупал: вдвое больше баллов за первую покупку. */
export function FriendGift() {
  const t = useT();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["referrals"], queryFn: api.referrals, staleTime: 60_000 });
  if (!q.data?.invited) return null;
  return (
    <button className="fgift" onClick={() => nav("/order")}>
      <CaseArt tier="small" size={84} />
      <span className="fgift-t">
        <b>{t("ref_gift_t")}</b>
        <span>{t("ref_gift_s", { n: q.data.friend_points })}</span>
      </span>
    </button>
  );
}
