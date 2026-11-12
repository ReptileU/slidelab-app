import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { haptic } from "../lib/tg";
import type { Work } from "../lib/types";
import { Img } from "./index";

const AUTO_MS = 3500;

/**
 * «Наши работы»: бесконечная карусель — сама листает по кругу, есть кнопки ‹ › и свайп.
 * По краям — копии последнего и первого слайда, после перехода на копию незаметно прыгаем на настоящий.
 */
export function WorksCarousel({ works }: { works: Work[] }) {
  const n = works.length;
  const slides = n > 1 ? [works[n - 1]!, ...works, works[0]!] : works;
  const [index, setIndex] = useState(n > 1 ? 1 : 0);
  const [animate, setAnimate] = useState(true);
  const [drag, setDrag] = useState(0);
  const start = useRef<{ x: number; y: number; w: number } | null>(null);
  const pausedUntil = useRef(0);
  const busy = useRef(false);

  // Автопрокрутка; после ручного листания — пауза
  useEffect(() => {
    if (n < 2) return;
    const id = setInterval(() => {
      if (Date.now() < pausedUntil.current || start.current || document.hidden) return;
      go(1, false);
    }, AUTO_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [n]);

  function go(step: number, manual = true) {
    if (busy.current) return;
    busy.current = true;
    setTimeout(() => (busy.current = false), 700); // если transitionend не придёт
    if (manual) {
      pausedUntil.current = Date.now() + AUTO_MS * 2;
      haptic.select();
    }
    setAnimate(true);
    setIndex((i) => i + step);
  }

  function onEnd() {
    busy.current = false;
    if (index === 0 || index === n + 1) {
      setAnimate(false);
      setIndex(index === 0 ? n : 1);
    }
  }

  // после «прыжка» без анимации — вернуть анимацию на следующий кадр
  useEffect(() => {
    if (animate) return;
    const id = requestAnimationFrame(() => requestAnimationFrame(() => setAnimate(true)));
    return () => cancelAnimationFrame(id);
  }, [animate]);

  function down(e: React.PointerEvent<HTMLDivElement>) {
    if (n < 2) return;
    start.current = { x: e.clientX, y: e.clientY, w: e.currentTarget.clientWidth };
  }
  function move(e: React.PointerEvent<HTMLDivElement>) {
    const s = start.current;
    if (!s) return;
    const dx = e.clientX - s.x;
    if (Math.abs(dx) > Math.abs(e.clientY - s.y)) setDrag(dx);
  }
  function up() {
    const s = start.current;
    start.current = null;
    if (!s) return;
    const threshold = s.w * 0.15;
    if (drag < -threshold) go(1);
    else if (drag > threshold) go(-1);
    setDrag(0);
  }

  const real = n > 1 ? (((index - 1) % n) + n) % n : 0;

  return (
    <div className="wc">
      <div
        className="wc-viewport"
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
        onPointerLeave={() => start.current && up()}
      >
        <div
          className="wc-track"
          style={{
            transform: `translateX(calc(${-index * 100}% + ${drag}px))`,
            transition: animate && !drag ? "transform 0.55s cubic-bezier(0.22, 0.8, 0.22, 1)" : "none",
          }}
          onTransitionEnd={onEnd}
        >
          {slides.map((w, i) => (
            <figure key={`${w.image}-${i}`} className="wc-slide" aria-hidden={i !== index}>
              <Img src={w.image} alt={w.title} />
              <figcaption className="work-caption">
                <div className="subhead" style={{ fontWeight: 600 }}>
                  {w.title}
                </div>
                <div className="footnote secondary">{w.style}</div>
              </figcaption>
            </figure>
          ))}
        </div>
        {n > 1 && (
          <div className="wc-navs">
            <button className="wc-nav prev" onClick={() => go(-1)} aria-label="‹">
              <ChevronLeft size={20} strokeWidth={2.5} />
            </button>
            <button className="wc-nav next" onClick={() => go(1)} aria-label="›">
              <ChevronRight size={20} strokeWidth={2.5} />
            </button>
          </div>
        )}
      </div>
      {n > 1 && (
        <div className="wc-dots">
          {works.map((w, i) => (
            <button
              key={w.image}
              className={i === real ? "on" : ""}
              aria-label={`${i + 1}`}
              onClick={() => {
                if (i === real || busy.current) return;
                pausedUntil.current = Date.now() + AUTO_MS * 2;
                haptic.select();
                setAnimate(true);
                busy.current = true;
                setTimeout(() => (busy.current = false), 700);
                setIndex(i + 1);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
