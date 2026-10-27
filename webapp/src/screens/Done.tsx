import { CheckCircle2 } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

import { useCatalog, useT } from "../lib/app";
import { openChat } from "../lib/tg";
import { Button } from "../ui";
import { MainButton } from "../ui/TelegramButtons";

export function Done() {
  const t = useT();
  const nav = useNavigate();
  const { id } = useParams();
  const catalog = useCatalog();

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
