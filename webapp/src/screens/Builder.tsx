import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Presentation, Sparkles } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { decksApi } from "../lib/api";
import { useT } from "../lib/app";
import { haptic } from "../lib/tg";
import { Button, Empty, Group, Section, Sheet, Skeleton, TextInput } from "../ui";
import { BackButton } from "../ui/TelegramButtons";

/** Список презентаций из конструктора и баланс кредитов ИИ. */
export function Builder() {
  const t = useT();
  const nav = useNavigate();
  const qc = useQueryClient();
  const decks = useQuery({ queryKey: ["decks"], queryFn: decksApi.list });
  const credits = useQuery({ queryKey: ["credits"], queryFn: decksApi.credits });
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const create = useMutation({
    mutationFn: () => decksApi.create(title.trim()),
    onSuccess: (deck) => {
      haptic.success();
      void qc.invalidateQueries({ queryKey: ["decks"] });
      setCreating(false);
      setTitle("");
      nav(`/builder/${deck.id}`);
    },
  });

  return (
    <div className="page no-tabbar builder-page">
      <BackButton onClick={() => nav(-1)} />
      <div className="row builder-head">
        <h1 className="large-title">{t("b_title")}</h1>
        {credits.data && <span className="credits-pill">{t("b_credits", { n: credits.data.balance })}</span>}
      </div>
      {credits.data && <p className="footnote secondary builder-sub">{t("b_credits_s", { n: credits.data.daily_cap })}</p>}

      <div className="builder-ai">
        <Sparkles size={18} />
        <span>{t("b_ai_soon")}</span>
      </div>

      <Button onClick={() => setCreating(true)}>
        <Plus size={18} /> {t("b_new")}
      </Button>

      <Section>
        {decks.isLoading ? (
          <Skeleton height={120} />
        ) : !decks.data?.length ? (
          <Empty icon={<Presentation />} title={t("b_empty_t")} text={t("b_empty_x")} />
        ) : (
          <Group>
            {decks.data.map((d) => (
              <button key={d.id} className="cell builder-deck" onClick={() => nav(`/builder/${d.id}`)}>
                <Presentation size={20} className="accent" />
                <span className="builder-deck-t">
                  <b>{d.title}</b>
                  <small className="secondary">{t("b_slides", { n: d.slides })}</small>
                </span>
                <span className="secondary">›</span>
              </button>
            ))}
          </Group>
        )}
      </Section>

      <Sheet open={creating} onClose={() => setCreating(false)} title={t("b_new")}>
        <TextInput value={title} onChange={setTitle} placeholder={t("b_new_ph")} maxLength={120} />
        <div style={{ height: 12 }} />
        <Button disabled={!title.trim() || create.isPending} onClick={() => create.mutate()}>
          {t("b_create")}
        </Button>
      </Sheet>
    </div>
  );
}
