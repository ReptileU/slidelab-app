import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import { useLang, useT } from "../lib/app";
import { alert, haptic } from "../lib/tg";
import type { Lang } from "../lib/types";
import { Group, Segmented, TextArea, TextInput } from "../ui";
import { DesignPicker, type DesignValue, FormBlock } from "../ui/FormKit";
import { BackButton, MainButton } from "../ui/TelegramButtons";

/**
 * Короткая заявка «бесплатная обложка» — для того, кто пришёл посмотреть, без длинной анкеты:
 * тема, как будет выглядеть (под тему / наш стиль / свой шаблон), язык и (по желанию) имя на титульном.
 * Ни объёма, ни срока, ни оплаты. Понравится обложка — та же заявка дооформляется в анкете (NewOrder ?complete=<id>).
 */
export function QuickCover() {
  const t = useT();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { lang } = useLang();
  const [params] = useSearchParams();
  const [topic, setTopic] = useState("");
  const [presLang, setPresLang] = useState<Lang>(lang);
  const [design, setDesign] = useState<DesignValue>(() => {
    const style = params.get("style");
    return { design: "ours", style_key: style, template_url: null };
  });
  const [name, setName] = useState("");
  const [tried, setTried] = useState(false);
  const [key] = useState(() => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`);
  const topicOk = topic.trim().length >= 3;
  const templateOk = design.design !== "own" || (design.template_url ?? "").trim().length > 3;
  const ready = topicOk && templateOk;

  const send = useMutation({
    mutationFn: () =>
      api.quickCover(
        {
          topic: topic.trim(),
          pres_lang: presLang,
          design: design.design,
          style_key: design.design === "ours" ? design.style_key : null,
          template_url: design.design === "own" ? design.template_url?.trim() || null : null,
          title_author: name.trim() || null,
        },
        key,
      ),
    onSuccess: (order) => {
      haptic.success();
      void qc.invalidateQueries({ queryKey: ["orders"] });
      nav(`/order/done/${order.id}?quick=1`, { replace: true });
    },
    onError: (e) => {
      haptic.error();
      void alert(e instanceof ApiError ? e.message : t("error"));
    },
  });

  return (
    <div className="page no-tabbar">
      <BackButton onClick={() => nav(-1)} />
      <div className="qc-hero">
        <span className="qc-badge">0 {t("sum")}</span>
        <h1 className="title1">{t("qc_title")}</h1>
        <p className="secondary">{t("qc_sub")}</p>
      </div>

      <FormBlock n={1} title={t("fb_topic_t")} hint={t("fb_topic_h")} need={tried && !topicOk} id="need-topic">
        <Group>
          <TextArea value={topic} onChange={setTopic} placeholder={t("qc_topic_ph")} maxLength={300} rows={3} />
        </Group>
      </FormBlock>

      <FormBlock n={2} title={t("fb_design_t")} hint={t("fb_design_h")}>
        <DesignPicker value={design} onChange={setDesign} need={tried && !templateOk} />
      </FormBlock>

      <FormBlock n={3} title={t("fb_lang_t")} hint={t("fb_lang_h")}>
        <Segmented
          value={presLang}
          onChange={setPresLang}
          options={[
            { value: "ru", label: "Русский" },
            { value: "uz", label: "O‘zbek" },
            { value: "en", label: "English" },
          ]}
        />
      </FormBlock>

      <FormBlock n={4} title={t("fb_name_t")} hint={t("fb_name_h")} optional>
        <Group>
          <TextInput value={name} onChange={setName} placeholder={t("qc_name_ph")} maxLength={80} />
        </Group>
      </FormBlock>

      <p className="footnote secondary qc-after">{t("qc_after")}</p>

      <MainButton
        text={t("qc_go")}
        muted={!ready}
        loading={send.isPending}
        onClick={() => {
          if (!ready) {
            haptic.error();
            setTried(true);
            document.getElementById("need-topic")?.scrollIntoView({ behavior: "smooth", block: "center" });
            return;
          }
          if (!send.isPending) send.mutate();
        }}
      />
    </div>
  );
}
