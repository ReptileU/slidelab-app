import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import { useCatalog, useLang, useT } from "../lib/app";
import { alert, haptic } from "../lib/tg";
import type { Lang } from "../lib/types";
import { Cell, Group, Section, Segmented, Sheet, TextArea, TextInput } from "../ui";
import { BackButton, MainButton } from "../ui/TelegramButtons";

/**
 * Короткая заявка «бесплатная обложка» — для того, кто пришёл посмотреть, без длинной анкеты:
 * тема, стиль, язык и (по желанию) имя на титульном слайде. Ни объёма, ни срока, ни оплаты.
 * Понравится обложка — та же заявка дооформляется в обычной анкете (NewOrder ?complete=<id>).
 */
export function QuickCover() {
  const t = useT();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { lang } = useLang();
  const [params] = useSearchParams();
  const catalog = useCatalog();
  const [topic, setTopic] = useState("");
  const [presLang, setPresLang] = useState<Lang>(lang);
  const [styleKey, setStyleKey] = useState<string | null>(params.get("style"));
  const [name, setName] = useState("");
  const [picker, setPicker] = useState(false);
  const [key] = useState(() => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`);
  const style = catalog.data?.styles.find((s) => s.key === styleKey);
  const ready = topic.trim().length >= 3;

  const send = useMutation({
    mutationFn: () =>
      api.quickCover(
        { topic: topic.trim(), pres_lang: presLang, style_key: styleKey, title_author: name.trim() || null },
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

      <Section title={t("qc_topic")}>
        <Group>
          <TextArea value={topic} onChange={setTopic} placeholder={t("qc_topic_ph")} maxLength={300} rows={2} />
        </Group>
      </Section>

      <Section title={t("qc_style")}>
        <Group>
          <Cell title={t("qc_style")} value={style?.name ?? t("f_style_none")} chevron onClick={() => setPicker(true)} />
        </Group>
      </Section>

      <Section title={t("qc_lang")}>
        <Segmented
          value={presLang}
          onChange={setPresLang}
          options={[
            { value: "ru", label: "Русский" },
            { value: "uz", label: "O‘zbek" },
            { value: "en", label: "English" },
          ]}
        />
      </Section>

      <Section title={t("qc_name")} footer={t("qc_after")}>
        <Group>
          <TextInput value={name} onChange={setName} placeholder={t("qc_name_ph")} maxLength={80} />
        </Group>
      </Section>

      <MainButton
        text={t("qc_go")}
        muted={!ready}
        loading={send.isPending}
        onClick={() => {
          if (!ready) {
            haptic.error();
            return;
          }
          if (!send.isPending) send.mutate();
        }}
      />

      <Sheet open={picker} onClose={() => setPicker(false)} title={t("qc_style")}>
        <Group>
          <Cell
            title={t("f_style_none")}
            checked={!styleKey}
            onClick={() => {
              setStyleKey(null);
              setPicker(false);
            }}
          />
          {catalog.data?.styles.map((s) => (
            <Cell
              key={s.key}
              icon={
                <img src={s.images[0]} alt="" style={{ width: 30, height: 30, objectFit: "cover", borderRadius: 7 }} />
              }
              iconBg="transparent"
              title={s.name}
              subtitle={s.hint}
              checked={styleKey === s.key}
              onClick={() => {
                setStyleKey(s.key);
                setPicker(false);
              }}
            />
          ))}
        </Group>
      </Sheet>
    </div>
  );
}
