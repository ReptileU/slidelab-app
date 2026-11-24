import { Check, FileUp, LayoutTemplate, Sparkles } from "lucide-react";
import { type ReactNode, useState } from "react";

import { useCatalog, useT } from "../lib/app";
import type { Design } from "../lib/types";

/**
 * Блок анкеты: номер шага, понятный заголовок и подсказка «зачем это», затем поля.
 * Так анкета читается сверху вниз как короткий план, а не как стена полей.
 */
export function FormBlock({
  n,
  title,
  hint,
  optional,
  need,
  id,
  children,
}: {
  n: number;
  title: ReactNode;
  hint?: ReactNode;
  optional?: boolean;
  need?: boolean;
  id?: string;
  children: ReactNode;
}) {
  const t = useT();
  return (
    <section className={`fblock${need ? " need" : ""}`} id={id}>
      <div className="fblock-h">
        <span className="fblock-n tabular">{n}</span>
        <div className="fblock-t">
          <b>
            {title}
            {optional && <em>{t("optional")}</em>}
          </b>
          {hint && <span>{hint}</span>}
        </div>
      </div>
      <div className="fblock-body">{children}</div>
    </section>
  );
}

export type DesignValue = { design: Design; style_key: string | null; template_url: string | null };
type Mode = "topic" | "ready" | "own";

/**
 * Как будет выглядеть презентация — главная особенность SlideLab, поэтому три понятные карточки, а не строка в списке:
 * «стиль под вашу тему» (по умолчанию, наша фишка), «готовый стиль из наших работ» (галерея прямо здесь),
 * «ваш шаблон» (ссылка; файл можно прислать в чат после заявки).
 */
export function DesignPicker({
  value,
  onChange,
  need,
}: {
  value: DesignValue;
  onChange: (v: DesignValue) => void;
  need?: boolean;
}) {
  const t = useT();
  const catalog = useCatalog();
  const styles = catalog.data?.styles ?? [];
  const [mode, setMode] = useState<Mode>(value.design === "own" ? "own" : value.style_key ? "ready" : "topic");

  const pick = (m: Mode) => {
    setMode(m);
    if (m === "topic") onChange({ design: "ours", style_key: null, template_url: null });
    // готовый стиль: сразу отмечаем первый, чтобы выбор был виден (дальше — касанием по миниатюре)
    if (m === "ready") onChange({ design: "ours", style_key: value.style_key ?? styles[0]?.key ?? null, template_url: null });
    if (m === "own") onChange({ design: "own", style_key: null, template_url: value.template_url });
  };

  return (
    <div className="dpick">
      <button type="button" className={`dopt hero${mode === "topic" ? " on" : ""}`} onClick={() => pick("topic")}>
        <span className="dopt-ic">
          <Sparkles size={20} />
        </span>
        <span className="dopt-t">
          <b>
            {t("dp_topic_t")} <i className="dopt-badge">{t("dp_topic_badge")}</i>
          </b>
          <span>{t("dp_topic_s")}</span>
          <span className="dopt-examples" aria-hidden>
            <span className="dx aral">
              <i />
              {t("dp_ex1")}
            </span>
            <span className="dx gta">
              <i />
              {t("dp_ex2")}
            </span>
            <span className="dx bank">
              <i />
              {t("dp_ex3")}
            </span>
          </span>
        </span>
        <span className="dopt-dot">{mode === "topic" && <Check size={14} strokeWidth={3} />}</span>
      </button>

      <button type="button" className={`dopt${mode === "ready" ? " on" : ""}`} onClick={() => pick("ready")}>
        <span className="dopt-ic">
          <LayoutTemplate size={20} />
        </span>
        <span className="dopt-t">
          <b>{t("dp_ready_t")}</b>
          <span>{t("dp_ready_s")}</span>
        </span>
        <span className="dopt-dot">{mode === "ready" && <Check size={14} strokeWidth={3} />}</span>
      </button>
      {mode === "ready" && (
        <div className="dgal">
          {styles.map((s) => (
            <button
              type="button"
              key={s.key}
              className={`dgal-i${value.style_key === s.key ? " on" : ""}`}
              onClick={() => onChange({ design: "ours", style_key: s.key, template_url: null })}
            >
              <img src={s.images[0]} alt="" loading="lazy" />
              <span>{s.name}</span>
              {value.style_key === s.key && (
                <i className="dgal-ok">
                  <Check size={13} strokeWidth={3} />
                </i>
              )}
            </button>
          ))}
        </div>
      )}

      <button type="button" className={`dopt${mode === "own" ? " on" : ""}`} onClick={() => pick("own")}>
        <span className="dopt-ic">
          <FileUp size={20} />
        </span>
        <span className="dopt-t">
          <b>{t("dp_own_t")}</b>
          <span>{t("dp_own_s")}</span>
        </span>
        <span className="dopt-dot">{mode === "own" && <Check size={14} strokeWidth={3} />}</span>
      </button>
      {mode === "own" && (
        <div className={`down${need ? " need" : ""}`}>
          <input
            className="field"
            value={value.template_url ?? ""}
            onChange={(e) => onChange({ design: "own", style_key: null, template_url: e.target.value })}
            placeholder={t("f_template_ph")}
            maxLength={500}
            inputMode="url"
          />
          <p>{t("f_template_hint")}</p>
        </div>
      )}
    </div>
  );
}
