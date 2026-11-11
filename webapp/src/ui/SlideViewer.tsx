import { Download, MapPin, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "../lib/api";
import { useT } from "../lib/app";
import { alert, haptic, tg } from "../lib/tg";
import type { Order, SlideMark } from "../lib/types";
import { Button, Group, Sheet, Skeleton, TextArea } from "./index";

type PdfDoc = { numPages: number; getPage(n: number): Promise<PdfPage> };
type PdfPage = {
  getViewport(o: { scale: number }): { width: number; height: number };
  render(o: { canvasContext: CanvasRenderingContext2D; viewport: unknown }): { promise: Promise<void> };
};

const RENDER_WIDTH = 1280; // px — чётко на телефоне и достаточно для снимков с метками

async function loadPdf(data: ArrayBuffer): Promise<PdfDoc> {
  // pdf.js тяжёлый — грузим только когда клиент открыл готовую презентацию
  const pdfjs = await import("pdfjs-dist/legacy/build/pdf");
  const worker = await import("pdfjs-dist/legacy/build/pdf.worker.min.js?url");
  pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
  return (await pdfjs.getDocument({ data, isEvalSupported: false }).promise) as unknown as PdfDoc;
}

async function renderPage(doc: PdfDoc, n: number): Promise<{ url: string; ratio: number }> {
  const page = await doc.getPage(n);
  const base = page.getViewport({ scale: 1 });
  const viewport = page.getViewport({ scale: RENDER_WIDTH / base.width });
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(viewport.width);
  canvas.height = Math.round(viewport.height);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas");
  await page.render({ canvasContext: ctx, viewport }).promise;
  return { url: canvas.toDataURL("image/jpeg", 0.86), ratio: canvas.height / canvas.width };
}

/** Снимок слайда с номерами меток — Claude увидит, где именно менять. */
async function annotate(src: string, marks: { x: number; y: number; n: number }[]): Promise<string> {
  const img = new Image();
  img.src = src;
  await img.decode();
  const canvas = document.createElement("canvas");
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext("2d");
  if (!ctx) return src;
  ctx.drawImage(img, 0, 0);
  const r = Math.max(18, canvas.width * 0.022);
  for (const m of marks) {
    const x = m.x * canvas.width;
    const y = m.y * canvas.height;
    ctx.beginPath();
    ctx.arc(x, y, r * 1.9, 0, Math.PI * 2);
    ctx.lineWidth = r * 0.28;
    ctx.strokeStyle = "#ff3b30";
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = "#ff3b30";
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.font = `700 ${Math.round(r * 1.2)}px system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(m.n), x, y + 1);
  }
  return canvas.toDataURL("image/jpeg", 0.82);
}

export function SlideViewer({ order, onSent }: { order: Order; onSent: (o: Order) => void }) {
  const t = useT();
  const [doc, setDoc] = useState<PdfDoc | null>(null);
  const [pages, setPages] = useState<Record<number, { url: string; ratio: number }>>({});
  const [failed, setFailed] = useState(false);
  const [current, setCurrent] = useState(1);
  const [picking, setPicking] = useState(false);
  const [draft, setDraft] = useState<{ slide: number; x: number; y: number } | null>(null);
  const [draftText, setDraftText] = useState("");
  const [marks, setMarks] = useState<SlideMark[]>([]);
  const [comment, setComment] = useState("");
  const [sending, setSending] = useState(false);
  const strip = useRef<HTMLDivElement>(null);
  const canEdit = order.status === "done";

  useEffect(() => {
    let alive = true;
    api
      .deckPdf(order.id)
      .then(loadPdf)
      .then((d) => alive && setDoc(d))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [order.id]);

  // рисуем текущий слайд и соседние — остальные по мере листания
  useEffect(() => {
    if (!doc) return;
    for (const n of [current, current + 1, current - 1, current + 2]) {
      if (n < 1 || n > doc.numPages || pages[n]) continue;
      renderPage(doc, n).then(
        (p) => setPages((prev) => ({ ...prev, [n]: p })),
        () => undefined,
      );
    }
  }, [doc, current, pages]);

  if (failed) return <p className="footnote secondary center">{t("v_fail")}</p>;
  if (!doc) return <Skeleton height={200} />;

  const total = doc.numPages;
  const ratio = pages[current]?.ratio ?? pages[1]?.ratio ?? 9 / 16;
  const numbered = marks.map((m, i) => ({ ...m, n: i + 1 }));

  function onScroll() {
    const el = strip.current;
    if (!el) return;
    const n = Math.round(el.scrollLeft / el.clientWidth) + 1;
    if (n !== current && n >= 1 && n <= total) {
      setCurrent(n);
      haptic.select();
    }
  }

  function go(n: number) {
    const el = strip.current;
    if (el) el.scrollTo({ left: (n - 1) * el.clientWidth, behavior: "smooth" });
  }

  function pick(e: React.PointerEvent<HTMLDivElement>, slide: number) {
    if (!picking) return;
    const box = e.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (e.clientX - box.left) / box.width));
    const y = Math.min(1, Math.max(0, (e.clientY - box.top) / box.height));
    haptic.tap();
    setDraft({ slide, x, y });
    setPicking(false);
  }

  async function send() {
    if (!marks.length && !comment.trim()) return;
    setSending(true);
    try {
      const bySlide = new Map<number, { x: number; y: number; n: number }[]>();
      numbered.forEach((m) => bySlide.set(m.slide, [...(bySlide.get(m.slide) ?? []), m]));
      const shots: string[] = [];
      for (const [slide, list] of bySlide) {
        const page = pages[slide] ?? (await renderPage(doc!, slide));
        shots.push(await annotate(page.url, list));
      }
      const o = await api.revise(order.id, comment.trim(), marks, shots.slice(0, 12));
      haptic.success();
      setMarks([]);
      setComment("");
      onSent(o);
    } catch (e) {
      haptic.error();
      alert(e instanceof ApiError ? e.message : t("error"));
    } finally {
      setSending(false);
    }
  }

  async function download(ext: "pdf" | "pptx") {
    try {
      const links = await api.downloads(order.id);
      const file = links.find((l) => l.name.toLowerCase().endsWith(`.${ext}`));
      if (!file) throw new Error();
      haptic.tap();
      if (tg?.downloadFile && tg.isVersionAtLeast("8.0")) tg.downloadFile({ url: file.url, file_name: file.name });
      else if (tg) tg.openLink(file.url);
      else window.open(file.url, "_blank");
    } catch {
      haptic.error();
      alert(t("error"));
    }
  }

  return (
    <div>
      <div className="viewer" style={{ ["--ratio" as string]: String(ratio) }}>
        <div className="viewer-strip" ref={strip} onScroll={onScroll}>
          {Array.from({ length: total }, (_, i) => i + 1).map((n) => (
            <div key={n} className="viewer-slide">
              <div className={`viewer-frame${picking ? " picking" : ""}`} onPointerUp={(e) => pick(e, n)}>
                {pages[n] ? <img src={pages[n].url} alt={`${n}`} draggable={false} /> : <div className="viewer-ph" />}
                {numbered
                  .filter((m) => m.slide === n)
                  .map((m) => (
                    <span key={m.n} className="viewer-pin" style={{ left: `${m.x * 100}%`, top: `${m.y * 100}%` }}>
                      {m.n}
                    </span>
                  ))}
                {draft?.slide === n && (
                  <span className="viewer-pin draft" style={{ left: `${draft.x * 100}%`, top: `${draft.y * 100}%` }}>
                    +
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
        <div className="row spread mt-8">
          <span className="footnote secondary">{t("v_slide", { n: current, total })}</span>
          <div className="row" style={{ gap: 6 }}>
            <button className="viewer-nav" disabled={current <= 1} onClick={() => go(current - 1)} aria-label="‹">
              ‹
            </button>
            <button className="viewer-nav" disabled={current >= total} onClick={() => go(current + 1)} aria-label="›">
              ›
            </button>
          </div>
        </div>
      </div>

      {canEdit && (
        <div className="mt-12">
          {picking ? (
            <div className="viewer-hint">
              <MapPin size={16} /> {t("v_mark_on")}
              <button className="viewer-hint-x" onClick={() => setPicking(false)}>
                {t("v_cancel")}
              </button>
            </div>
          ) : (
            <Button kind="tinted" onClick={() => setPicking(true)}>
              <MapPin size={17} /> {t("v_mark")}
            </Button>
          )}
        </div>
      )}

      {marks.length > 0 && (
        <div className="mt-16">
          <div className="footnote secondary" style={{ margin: "0 4px 6px", textTransform: "uppercase", letterSpacing: ".06em" }}>
            {t("v_marks")}
          </div>
          <Group>
            {numbered.map((m, i) => (
              <div key={i} className="viewer-mark" onClick={() => go(m.slide)}>
                <span className="viewer-pin static">{m.n}</span>
                <div className="grow">
                  <div className="caption secondary">{t("v_slide", { n: m.slide, total })}</div>
                  <div className="subhead">{m.text}</div>
                </div>
                <button
                  aria-label="×"
                  onClick={(e) => {
                    e.stopPropagation();
                    setMarks((list) => list.filter((_, j) => j !== i));
                  }}
                >
                  <X size={18} />
                </button>
              </div>
            ))}
          </Group>
        </div>
      )}

      {canEdit && (marks.length > 0 || comment) && (
        <div className="mt-12">
          <Group>
            <TextArea value={comment} onChange={setComment} placeholder={t("v_comment_ph")} maxLength={1000} rows={2} />
          </Group>
          <div className="mt-12">
            <Button disabled={sending || (!marks.length && !comment.trim())} onClick={send}>
              {sending ? "…" : t("v_send", { n: marks.length || 1 })}
            </Button>
          </div>
        </div>
      )}

      <div className="row mt-16" style={{ gap: 8 }}>
        <Button kind="plain" small onClick={() => download("pdf")}>
          <Download size={16} /> {t("v_dl", { ext: "PDF" })}
        </Button>
        <Button kind="plain" small onClick={() => download("pptx")}>
          <Download size={16} /> {t("v_dl", { ext: "PPTX" })}
        </Button>
      </div>

      <Sheet open={draft !== null} onClose={() => setDraft(null)} title={draft ? t("v_what", { n: draft.slide }) : ""}>
        <Group>
          <TextArea value={draftText} onChange={setDraftText} placeholder={t("v_what_ph")} maxLength={500} rows={3} autoFocus />
        </Group>
        <div className="mt-16">
          <Button
            disabled={!draftText.trim()}
            onClick={() => {
              if (!draft) return;
              setMarks((list) => [...list, { ...draft, text: draftText.trim() }]);
              setDraft(null);
              setDraftText("");
              haptic.success();
            }}
          >
            {t("v_add")}
          </Button>
        </div>
      </Sheet>
    </div>
  );
}
