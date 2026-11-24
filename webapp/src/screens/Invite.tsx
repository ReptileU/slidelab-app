import { useQuery } from "@tanstack/react-query";
import { Check, Copy, Send, UserPlus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api";
import { useLang, useT } from "../lib/app";
import { formatDate } from "../lib/i18n";
import { haptic, openTelegramUrl, shareMessage } from "../lib/tg";
import { Section, Skeleton, Toast } from "../ui";
import { CaseArt } from "../ui/PointsCase";
import { BackButton } from "../ui/TelegramButtons";

/**
 * Пригласить друга: другу — вдвое больше баллов за первую покупку (сразу бронзовый кейс),
 * пригласившему — баллы, когда друг заплатит, и бонусы за 3 и 10 оплативших друзей.
 */
export function Invite() {
  const t = useT();
  const { lang } = useLang();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["referrals"], queryFn: api.referrals });
  const [toast, setToast] = useState<string | null>(null);
  const d = q.data;

  const [sharing, setSharing] = useState(false);
  // Отправляем рекламную карточку (наши работы + подарок + кнопка), а не голую ссылку
  const share = async () => {
    if (!d || sharing) return;
    haptic.tap();
    setSharing(true);
    try {
      const { prepared_id } = await api.shareInvite();
      const sent = prepared_id ? await shareMessage(prepared_id) : null;
      if (sent === null) setToast(t("ref_in_chat")); // старый Telegram: карточка уже в чате с ботом — переслать оттуда
    } catch {
      const text = t("ref_share_text", { n: d.friend_points });
      openTelegramUrl(`https://t.me/share/url?url=${encodeURIComponent(d.link)}&text=${encodeURIComponent(text)}`);
    } finally {
      setSharing(false);
    }
  };
  const copy = async () => {
    if (!d) return;
    try {
      await navigator.clipboard.writeText(d.link);
      haptic.success();
      setToast(t("ref_copied"));
    } catch {
      setToast(d.link);
    }
  };

  const top = d ? Math.max(...d.milestones.map((m) => m.friends)) : 10;
  const next = d?.milestones.find((m) => !m.reached);

  return (
    <div className="page no-tabbar">
      <BackButton onClick={() => nav(-1)} />

      <div className="inv-hero">
        <div className="inv-chests" aria-hidden>
          <CaseArt tier="small" size={110} />
          <CaseArt tier="large" size={140} />
          <CaseArt tier="medium" size={110} />
        </div>
        <h1>{t("ref_title")}</h1>
        <p>{t("ref_sub")}</p>
      </div>

      {!d ? (
        <Skeleton height={220} />
      ) : (
        <>
          {/* что получит каждый */}
          <div className="inv-deal">
            <div className="inv-side you">
              <span className="inv-who">{t("ref_you")}</span>
              <b className="tabular">+{d.inviter_points}</b>
              <span>{t("ref_you_s")}</span>
            </div>
            <div className="inv-plus">+</div>
            <div className="inv-side friend">
              <span className="inv-who">{t("ref_friend")}</span>
              <b className="tabular">{d.friend_points}</b>
              <span>{t("ref_friend_s")}</span>
            </div>
          </div>

          {d.milestones.some((m) => m.prize === "coupon") && (
            <div className="inv-free">
              <span className="inv-free-n tabular">3</span>
              <span className="inv-free-t">
                <b>{t("ref_free_t")}</b>
                <span>{t("ref_free_s")}</span>
              </span>
            </div>
          )}

          <div className="inv-actions">
            <button className="inv-share" disabled={sharing} onClick={() => void share()}>
              {sharing ? <span className="btn-spinner" /> : <Send size={18} />} {t("ref_share")}
            </button>
            <button className="inv-copy" onClick={() => void copy()} aria-label={t("ref_copy")}>
              <Copy size={18} />
            </button>
          </div>

          {/* бонусы за количество оплативших друзей */}
          <Section title={t("ref_goals")}>
            <div className="inv-goals">
              <div className="inv-track">
                <i style={{ width: `${Math.min(100, (d.paid / top) * 100)}%` }} />
                {d.milestones.map((m) => (
                  <span key={m.friends} className={m.reached ? "on" : ""} style={{ left: `${(m.friends / top) * 100}%` }}>
                    <em>
                      {m.prize === "coupon" ? t("ref_ms_coupon", { n: m.friends }) : `${m.friends} · +${m.points}`}
                    </em>
                  </span>
                ))}
              </div>
              <p className="inv-next">
                {next
                  ? next.prize === "coupon"
                    ? t("ref_next_coupon", { n: next.friends - d.paid })
                    : t("ref_next", { n: next.friends - d.paid, pts: next.points })
                  : t("ref_all_goals")}
              </p>
              <div className="inv-stats">
                <div>
                  <b className="tabular">{d.paid}</b>
                  <span>{t("ref_paid")}</span>
                </div>
                <div>
                  <b className="tabular">{d.earned}</b>
                  <span>{t("ref_earned")}</span>
                </div>
              </div>
            </div>
          </Section>

          <Section title={t("ref_friends")}>
            {d.friends.length === 0 ? (
              <div className="inv-empty">
                <UserPlus size={22} />
                <span>{t("ref_empty")}</span>
              </div>
            ) : (
              <div className="inv-list">
                {d.friends.map((f, i) => (
                  <div key={i} className={`inv-row${f.paid_at ? " paid" : ""}`}>
                    <span className="inv-ava">{f.name.slice(0, 1).toUpperCase()}</span>
                    <div className="inv-row-t">
                      <b>{f.name}</b>
                      <span>
                        {f.paid_at
                          ? t("ref_row_paid", { date: formatDate(f.paid_at, lang) })
                          : t("ref_row_wait", { date: formatDate(f.joined_at, lang) })}
                      </span>
                    </div>
                    {f.paid_at ? (
                      <span className="inv-pts tabular">
                        <Check size={14} /> +{f.points}
                      </span>
                    ) : (
                      <span className="inv-wait">{t("ref_waiting", { n: d.inviter_points })}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Section>
          <p className="lucky-note">{t("ref_rules")}</p>
        </>
      )}
      <Toast text={toast} onDone={() => setToast(null)} />
    </div>
  );
}
