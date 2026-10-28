import { ChevronDown, Search } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCatalog, useT } from "../lib/app";
import { haptic } from "../lib/tg";
import { Group, Section, Skeleton, Toast } from "../ui";
import { BackButton, MainButton } from "../ui/TelegramButtons";
import { AskSheet } from "./Profile";

export function Help() {
  const t = useT();
  const nav = useNavigate();
  const catalog = useCatalog();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [asking, setAsking] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const q = query.trim().toLowerCase();
  const items = (catalog.data?.faq ?? []).filter((f) => !q || `${f.q} ${f.a}`.toLowerCase().includes(q));

  return (
    <div className="page no-tabbar">
      <BackButton onClick={() => nav(-1)} />
      <h1 className="large-title" style={{ margin: "8px 0 16px" }}>
        {t("help_t")}
      </h1>

      <div className="row" style={{ background: "var(--fill)", borderRadius: 10, padding: "0 10px", height: 36, gap: 6, marginBottom: 20 }}>
        <Search size={17} className="secondary" />
        <input className="field" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("search_ph")} />
      </div>

      <Section footer={q && items.length === 0 ? t("nothing_found") : undefined}>
        {catalog.isLoading ? (
          <Skeleton height={300} />
        ) : (
          <Group>
            {items.map((f, i) => (
              <button
                key={f.q}
                className="cell"
                style={{ flexDirection: "column", alignItems: "stretch" }}
                onClick={() => {
                  haptic.select();
                  setOpen(open === i ? null : i);
                }}
              >
                <span className="row spread">
                  <span className="cell-title">{f.q}</span>
                  <ChevronDown size={18} className="secondary" style={{ transform: open === i || q ? "rotate(180deg)" : "none", transition: "transform .2s", flex: "0 0 auto" }} />
                </span>
                {(open === i || !!q) && <span className="subhead secondary" style={{ marginTop: 6 }}>{f.a}</span>}
              </button>
            ))}
          </Group>
        )}
      </Section>

      <MainButton text={t("ask_t")} onClick={() => setAsking(true)} />
      <AskSheet open={asking} onClose={() => setAsking(false)} onSent={() => setToast(t("ask_sent"))} />
      <Toast text={toast} onDone={() => setToast(null)} />
    </div>
  );
}
