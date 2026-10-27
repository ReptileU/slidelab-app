import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useCatalog, useT } from "../lib/app";
import type { Key } from "../lib/i18n";
import type { Style } from "../lib/types";
import { BackButton } from "../ui/TelegramButtons";
import { Button, Chips, Img, Section, Sheet, Skeleton } from "../ui";

const FILTERS = ["all", "study", "business", "dark", "light"] as const;
type Filter = (typeof FILTERS)[number];

export function Styles() {
  const t = useT();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const catalog = useCatalog();
  const [filter, setFilter] = useState<Filter>("all");
  const styles = catalog.data?.styles ?? [];
  const shown = filter === "all" ? styles : styles.filter((s) => s.tags.includes(filter));
  const open = styles.find((s) => s.key === params.get("open")) ?? null;

  return (
    <div className="page no-tabbar">
      <BackButton onClick={() => (open ? setParams({}) : nav(-1))} />
      <h1 className="large-title" style={{ margin: "8px 0 16px" }}>
        {t("styles_t")}
      </h1>
      <Section>
        <Chips
          value={filter}
          onChange={setFilter}
          options={FILTERS.map((f) => ({ value: f, label: t(`filter_${f}` as Key) }))}
        />
      </Section>
      <div className="style-grid">
        {catalog.isLoading && [0, 1, 2, 3].map((i) => <Skeleton key={i} height={120} />)}
        {shown.map((s) => (
          <button key={s.key} className="style-card" onClick={() => setParams({ open: s.key })}>
            <Img src={s.images[0]} alt={s.name} />
            <div className="name">{s.name}</div>
            <div className="hint">{s.hint}</div>
          </button>
        ))}
      </div>

      <StyleSheet style={open} onClose={() => setParams({})} onPick={(key) => nav(`/order?style=${key}`, { replace: true })} />
    </div>
  );
}

function StyleSheet({ style, onClose, onPick }: { style: Style | null; onClose: () => void; onPick: (key: string) => void }) {
  const t = useT();
  return (
    <Sheet open={!!style} onClose={onClose} title={style?.name}>
      {style && (
        <div className="stack gap-12">
          <div className="row" style={{ gap: 8 }}>
            <span className="badge gray">{style.is_real_work ? t("style_real") : t("style_example")}</span>
            <span className="footnote secondary">{style.hint}</span>
          </div>
          {style.images.map((src) => (
            <Img key={src} src={src} alt="" className="thumb" />
          ))}
          <p className="footnote secondary center">{t("style_note")}</p>
          <Button onClick={() => onPick(style.key)}>{t("style_pick")}</Button>
        </div>
      )}
    </Sheet>
  );
}
