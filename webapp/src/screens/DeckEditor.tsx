import { BarChart3, ImagePlus, Play, Plus, Sparkles, Trash2, Type, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, decksApi } from "../lib/api";
import { useT } from "../lib/app";
import type { Key } from "../lib/i18n";
import { confirm, haptic } from "../lib/tg";
import type { AnimPreset, Deck, DeckAsset, DeckElement, DeckSlide } from "../lib/types";
import { Button, Chips, Sheet, Skeleton, TextArea, Toast } from "../ui";
import { AssistantSheet, captionEl } from "../ui/AssistantSheet";
import { SlideCanvas } from "../ui/SlideCanvas";
import { BackButton } from "../ui/TelegramButtons";

const uid = () => Math.random().toString(36).slice(2, 12);
const SAVE_DELAY = 1200;
const ANIMS: AnimPreset[] = ["none", "fade", "fade-up", "zoom", "slide-left", "grow"];

/** Фото → WebP (или PNG, если браузер не умеет WebP) до 2000 px: на сервер уходит уже лёгкий файл. */
async function shrinkForDeck(file: File): Promise<string> {
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    const scale = Math.min(1, 2000 / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.naturalWidth * scale);
    canvas.height = Math.round(img.naturalHeight * scale);
    canvas.getContext("2d")?.drawImage(img, 0, 0, canvas.width, canvas.height);
    const webp = canvas.toDataURL("image/webp", 0.88);
    return webp.startsWith("data:image/webp") ? webp : canvas.toDataURL("image/png");
  } finally {
    URL.revokeObjectURL(url);
  }
}

function newSlide(text: string): DeckSlide {
  return {
    id: uid(),
    layout: "blank",
    elements: [
      {
        id: uid(),
        type: "text",
        role: "title",
        box: { x: 0.08, y: 0.1, w: 0.84, h: 0.18 },
        text,
        style: { size: 44, weight: 700 },
        anim: { preset: "fade-up" },
      },
    ],
  };
}

export function DeckEditor() {
  const t = useT();
  const nav = useNavigate();
  const id = Number(useParams().id);

  const [deck, setDeck] = useState<Deck | null>(null);
  const [current, setCurrent] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [assets, setAssets] = useState<Record<number, string>>({});
  const [status, setStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [toast, setToast] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [playing, setPlaying] = useState<number | null>(null);
  const [playKey, setPlayKey] = useState(0);
  const [assist, setAssist] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Версия и очередь сохранений: правки уходят по одной, каждая — с версией после предыдущей
  const version = useRef(1);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const timers = useRef<Record<string, number>>({});

  const load = useCallback(async () => {
    const d = await decksApi.get(id);
    version.current = d.version;
    setDeck(d);
    const list = await decksApi.assets(id);
    setAssets(Object.fromEntries(list.map((a) => [a.id, decksApi.assetSrc(a.url)])));
  }, [id]);

  useEffect(() => {
    void load().catch(() => nav("/builder", { replace: true }));
  }, [load, nav]);

  /** Поставить действие в очередь сохранения; при конфликте версий — перезагрузить презентацию. */
  const enqueue = useCallback(
    (op: (v: number) => Promise<{ version: number }>) => {
      setStatus("saving");
      queue.current = queue.current
        .then(async () => {
          const res = await op(version.current);
          version.current = res.version;
          setStatus("saved");
        })
        .catch(async (e: unknown) => {
          if (e instanceof ApiError && e.code === "version_conflict") {
            setToast(t("b_conflict"));
            await load();
          } else {
            setToast(e instanceof Error ? e.message : String(e));
          }
          setStatus("idle");
        });
    },
    [load, t],
  );

  /** Изменить слайд локально сразу, на сервер — через паузу (не на каждую букву). */
  const changeSlide = (slide: DeckSlide) => {
    setDeck((d) => (d ? { ...d, body: { ...d.body, slides: d.body.slides.map((s) => (s.id === slide.id ? slide : s)) } } : d));
    window.clearTimeout(timers.current[slide.id]);
    setStatus("saving");
    timers.current[slide.id] = window.setTimeout(() => {
      delete timers.current[slide.id];
      enqueue((v) => decksApi.saveSlide(id, v, slide));
    }, SAVE_DELAY);
  };

  // Ушли с экрана — отправить отложенные правки сразу
  const latest = useRef(deck);
  latest.current = deck;
  useEffect(
    () => () => {
      for (const sid of Object.keys(timers.current)) {
        window.clearTimeout(timers.current[sid]);
        const s = latest.current?.body.slides.find((x) => x.id === sid);
        if (s) enqueue((v) => decksApi.saveSlide(id, v, s));
      }
    },
    [enqueue, id],
  );

  if (!deck) {
    return (
      <div className="page no-tabbar">
        <Skeleton height={220} />
      </div>
    );
  }

  const slides = deck.body.slides;
  const slide = slides[Math.min(current, slides.length - 1)];
  const element = slide?.elements.find((e) => e.id === selected) ?? null;
  const assetUrl = (aid: number) => assets[aid];

  const addSlide = () => {
    haptic.tap();
    const s = newSlide(t("b_new_text"));
    const after = slide?.id ?? null;
    const pos = slide ? slides.indexOf(slide) + 1 : 0;
    setDeck({ ...deck, body: { ...deck.body, slides: [...slides.slice(0, pos), s, ...slides.slice(pos)] } });
    setCurrent(pos);
    setSelected(null);
    enqueue((v) => decksApi.insertSlide(id, v, s, after));
  };

  const removeSlide = async () => {
    if (!slide || !(await confirm(t("b_delete_slide_q")))) return;
    const rest = slides.filter((s) => s.id !== slide.id);
    setDeck({ ...deck, body: { ...deck.body, slides: rest } });
    setCurrent(Math.max(0, current - 1));
    setSelected(null);
    window.clearTimeout(timers.current[slide.id]);
    delete timers.current[slide.id];
    enqueue((v) => decksApi.deleteSlide(id, v, slide.id));
  };

  const addElement = (el: DeckElement) => {
    if (!slide) return;
    haptic.tap();
    changeSlide({ ...slide, elements: [...slide.elements, el] });
    setSelected(el.id);
  };

  /** Несколько элементов сразу (из помощника): один снимок слайда — одно сохранение. */
  const addElements = (els: DeckElement[], asNewSlide = false) => {
    if (asNewSlide || !slide) {
      const s: DeckSlide = { id: uid(), layout: "blank", elements: els };
      const pos = slide ? slides.indexOf(slide) + 1 : 0;
      setDeck({ ...deck, body: { ...deck.body, slides: [...slides.slice(0, pos), s, ...slides.slice(pos)] } });
      setCurrent(pos);
      setSelected(null);
      const after = slide?.id ?? null;
      enqueue((v) => decksApi.insertSlide(id, v, s, after));
      return;
    }
    changeSlide({ ...slide, elements: [...slide.elements, ...els] });
    setSelected(null);
  };

  /** Слайды из плана: каждый пункт — новый слайд с заголовком, после текущего, по порядку. */
  const addSlides = (titles: string[]) => {
    const made = titles.map((title) => newSlide(title));
    const pos = slide ? slides.indexOf(slide) + 1 : 0;
    setDeck({ ...deck, body: { ...deck.body, slides: [...slides.slice(0, pos), ...made, ...slides.slice(pos)] } });
    let after = slide?.id ?? null;
    for (const s of made) {
      const prev = after;
      enqueue((v) => decksApi.insertSlide(id, v, s, prev));
      after = s.id;
    }
    setCurrent(pos);
    setSelected(null);
  };

  const photoElement = (asset: DeckAsset): DeckElement => {
    const ratio = asset.height / asset.width;
    const w = Math.min(0.5, 0.6 / ratio / (16 / 9));
    return {
      id: uid(),
      type: "image",
      asset_id: asset.id,
      box: { x: 0.5 - w / 2, y: 0.25, w, h: Math.min(0.6, ((w * 16) / 9) * ratio) },
      anim: { preset: "fade" },
    };
  };

  const addFoundPhoto = (asset: DeckAsset, caption: string) => {
    setAssets((a) => ({ ...a, [asset.id]: decksApi.assetSrc(asset.url) }));
    addElements([photoElement(asset), captionEl(caption)]);
  };

  const patchElement = (patch: Partial<DeckElement>) => {
    if (!slide || !element) return;
    changeSlide({ ...slide, elements: slide.elements.map((e) => (e.id === element.id ? { ...e, ...patch } : e)) });
  };

  const removeElement = () => {
    if (!slide || !element) return;
    changeSlide({ ...slide, elements: slide.elements.filter((e) => e.id !== element.id) });
    setSelected(null);
  };

  const onFile = async (file: File | undefined) => {
    if (!file || !slide) return;
    setUploading(true);
    try {
      const asset = await decksApi.upload(id, await shrinkForDeck(file));
      setAssets((a) => ({ ...a, [asset.id]: decksApi.assetSrc(asset.url) }));
      addElement(photoElement(asset));
    } catch (e) {
      setToast(e instanceof Error ? e.message : t("b_upload_err"));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const removeDeck = async () => {
    if (!(await confirm(t("b_delete_deck_q")))) return;
    await decksApi.remove(id);
    nav("/builder", { replace: true });
  };

  if (playing !== null) {
    const s = slides[playing];
    const next = () => {
      if (playing + 1 >= slides.length) setPlaying(null);
      else {
        setPlaying(playing + 1);
        setPlayKey((k) => k + 1);
      }
    };
    return (
      <div className="deck-play" onClick={next}>
        <button
          className="deck-play-close"
          onClick={(e) => {
            e.stopPropagation();
            setPlaying(null);
          }}
          aria-label="close"
        >
          <X size={20} />
        </button>
        {s && <SlideCanvas slide={s} theme={deck.body.theme} assetUrl={assetUrl} play playKey={playKey} />}
        <span className="deck-play-n">
          {playing + 1} / {slides.length}
        </span>
      </div>
    );
  }

  return (
    <div className="page no-tabbar editor-page">
      <BackButton onClick={() => nav("/builder")} />
      <div className="row editor-head">
        <h1 className="title2 editor-title">{deck.title}</h1>
        <span className="footnote secondary">{status === "saving" ? t("b_saving") : status === "saved" ? t("b_saved") : ""}</span>
      </div>

      {slide ? (
        <SlideCanvas
          slide={slide}
          theme={deck.body.theme}
          assetUrl={assetUrl}
          selected={selected}
          onSelect={setSelected}
          className="editor-canvas"
        />
      ) : (
        <div className="editor-canvas slide-canvas" />
      )}
      <p className="footnote secondary editor-hint">{t("b_tap_hint")}</p>

      <button className="assist-open" onClick={() => (haptic.tap(), setAssist(true))}>
        <Sparkles size={18} />
        <span>
          <b>{t("a_btn")}</b>
          <small>
            {t("a_plan")} · {t("a_facts")} · {t("a_papers")} · {t("a_photos")} · {t("a_stats")}
          </small>
        </span>
      </button>

      <div className="editor-tools">
        <button onClick={() => addElement({ id: uid(), type: "text", role: "body", box: { x: 0.08, y: 0.35, w: 0.84, h: 0.4 }, text: t("b_new_text"), style: { size: 24 }, anim: { preset: "fade" } })}>
          <Type size={20} />
          <span>{t("b_add_text")}</span>
        </button>
        <button onClick={() => fileRef.current?.click()} disabled={uploading}>
          <ImagePlus size={20} />
          <span>{uploading ? "…" : t("b_add_image")}</span>
        </button>
        <button
          onClick={() =>
            addElement({
              id: uid(),
              type: "chart",
              box: { x: 0.1, y: 0.32, w: 0.8, h: 0.6 },
              chart: { kind: "bar", labels: ["2021", "2022", "2023", "2024"], series: [{ name: t("b_chart_demo"), values: [12, 19, 27, 40] }] },
              anim: { preset: "grow" },
            })
          }
        >
          <BarChart3 size={20} />
          <span>{t("b_add_chart")}</span>
        </button>
        <button
          onClick={() => {
            setPlaying(Math.min(current, slides.length - 1));
            setPlayKey((k) => k + 1);
          }}
          disabled={!slides.length}
        >
          <Play size={20} />
          <span>{t("b_play")}</span>
        </button>
      </div>
      <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={(e) => void onFile(e.target.files?.[0])} />

      <div className="editor-strip">
        {slides.map((s, i) => (
          <button
            key={s.id}
            className={`editor-thumb${i === current ? " active" : ""}`}
            onClick={() => {
              haptic.select();
              setCurrent(i);
              setSelected(null);
            }}
          >
            <SlideCanvas slide={s} theme={deck.body.theme} assetUrl={assetUrl} />
            <span>{i + 1}</span>
          </button>
        ))}
        <button className="editor-thumb editor-thumb-add" onClick={addSlide} aria-label={t("b_add_slide")}>
          <Plus size={22} />
        </button>
      </div>

      <div className="editor-danger">
        <Button kind="plain" small onClick={() => void removeSlide()} disabled={!slide}>
          <Trash2 size={16} /> {t("b_delete_slide")}
        </Button>
        <Button kind="plain" small onClick={() => void removeDeck()}>
          {t("b_delete_deck")}
        </Button>
      </div>

      <Sheet open={!!element} onClose={() => setSelected(null)} title={element?.type === "text" ? t("b_edit_text") : t("b_anim")}>
        {element?.type === "text" && (
          <TextArea value={element.text ?? ""} onChange={(text) => patchElement({ text })} maxLength={3000} rows={4} />
        )}
        {element && (
          <>
            <div className="field-label" style={{ margin: "14px 0 8px" }}>
              {t("b_anim")}
            </div>
            <Chips
              options={ANIMS.map((a) => ({ value: a, label: t(`b_anim_${a.replace("-", "_")}` as Key) }))}
              value={element.anim?.preset ?? "none"}
              onChange={(preset) => patchElement({ anim: { ...element.anim, preset } })}
            />
            <div style={{ height: 16 }} />
            <div className="row">
              <Button kind="gray" onClick={removeElement}>
                {t("b_remove_el")}
              </Button>
              <Button onClick={() => setSelected(null)}>{t("b_save")}</Button>
            </div>
          </>
        )}
      </Sheet>
      <AssistantSheet
        open={assist}
        onClose={() => setAssist(false)}
        deckId={id}
        topic={deck.title}
        onElements={addElements}
        onSlides={addSlides}
        onPhoto={addFoundPhoto}
      />
      <Toast text={toast} onDone={() => setToast(null)} />
    </div>
  );
}
