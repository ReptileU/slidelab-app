import { BellRing, CheckCircle2, DoorOpen, Wallet } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { useCatalog, useT } from "../lib/app";
import { openChat } from "../lib/tg";
import { Button } from "../ui";
import { MainButton } from "../ui/TelegramButtons";

export function Done() {
  const t = useT();
  const nav = useNavigate();
  const { id } = useParams();
  const catalog = useCatalog();
  const [params] = useSearchParams();

  // короткая заявка на обложку: главное — объяснить, что можно уходить и ничего не потеряется
  if (params.get("quick") === "1")
    return (
      <div className="page no-tabbar" style={{ display: "grid", minHeight: "80vh", alignContent: "center" }}>
        <div className="center">
          <CheckCircle2 size={72} strokeWidth={1.5} className="accent" style={{ margin: "0 auto 18px" }} />
          <h1 className="title1">{t("qd_t")}</h1>
          <p className="subhead secondary" style={{ margin: "10px 8px 22px" }}>
            {t("qd_s")}
          </p>
        </div>
        <div className="qd-list">
          <div className="qd-row">
            <DoorOpen size={22} />
            <span>
              <b>{t("qd_leave_t")}</b>
              {t("qd_leave_s")}
            </span>
          </div>
          <div className="qd-row">
            <BellRing size={22} />
            <span>
              <b>{t("qd_send_t")}</b>
              {t("qd_send_s")}
            </span>
          </div>
          <div className="qd-row">
            <Wallet size={22} />
            <span>
              <b>{t("qd_pay_t")}</b>
              {t("qd_pay_s")}
            </span>
          </div>
        </div>
        <div className="center mt-16">
          <Button kind="plain" onClick={() => nav(`/orders/${id}`, { replace: true })}>
            {t("qd_open")}
          </Button>
        </div>
        <MainButton text={t("qd_ok")} onClick={() => nav("/", { replace: true })} />
      </div>
    );

  return (
    <div className="page no-tabbar" style={{ display: "grid", minHeight: "80vh", alignContent: "center" }}>
      <div className="center">
        <CheckCircle2 size={72} strokeWidth={1.5} className="accent" style={{ margin: "0 auto 20px" }} />
        <h1 className="title1">{t("done_t", { id: id ?? "" })}</h1>
        <p className="subhead secondary" style={{ margin: "12px 8px 24px" }}>
          {t("done_x")}
        </p>
        <Button kind="plain" onClick={() => nav(`/orders/${id}`, { replace: true })}>
          {t("to_order")}
        </Button>
      </div>
      <MainButton text={t("open_chat")} onClick={() => openChat(catalog.data?.bot_username ?? "slidelab_order_bot")} />
    </div>
  );
}
