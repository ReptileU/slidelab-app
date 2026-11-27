import type { CSSProperties, MouseEvent } from "react";

import type { DeckElement, DeckSlide, DeckTheme } from "../lib/types";

/**
 * Слайд 16:9 из JSON конструктора. Координаты — доли (0..1), размер шрифта — в пунктах слайда шириной 960 pt
 * (как PPTX 13,33″), поэтому миниатюра и полный экран выглядят одинаково.
 * play — проиграть анимации элементов (смена ключа перезапускает их).
 */
export function SlideCanvas({
  slide,
  theme,
  assetUrl,
  play = false,
  playKey = 0,
  selected,
  onSelect,
  className = "",
}: {
  slide: DeckSlide;
  theme: DeckTheme;
  assetUrl: (id: number) => string | undefined;
  play?: boolean;
  playKey?: number;
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  className?: string;
}) {
  const color = (c: string | undefined, fallback: string) =>
    !c ? fallback : c.startsWith("#") ? c : (theme.palette as Record<string, string>)[c] ?? fallback;
  const bg = slide.bg_asset_id ? assetUrl(slide.bg_asset_id) : undefined;
  return (
    <div
      className={`slide-canvas${className ? ` ${className}` : ""}`}
      style={{
        background: color(slide.bg, theme.palette.bg),
        color: theme.palette.fg,
        backgroundImage: bg ? `url(${bg})` : undefined,
        fontFamily: `"${theme.fonts.body}", system-ui, sans-serif`,
      }}
      onClick={onSelect ? () => onSelect(null) : undefined}
    >
      {slide.elements.map((el) => (
        <Element
          key={`${el.id}-${play ? playKey : "static"}`}
          el={el}
          theme={theme}
          color={color}
          src={el.asset_id ? assetUrl(el.asset_id) : undefined}
          play={play}
          selected={selected === el.id}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}

function Element({
  el,
  theme,
  color,
  src,
  play,
  selected,
  onSelect,
}: {
  el: DeckElement;
  theme: DeckTheme;
  color: (c: string | undefined, fallback: string) => string;
  src?: string;
  play: boolean;
  selected: boolean;
  onSelect?: (id: string | null) => void;
}) {
  const anim = el.anim?.preset && el.anim.preset !== "none" && play ? ` anim-${el.anim.preset}` : "";
  const style: CSSProperties = {
    left: `${el.box.x * 100}%`,
    top: `${el.box.y * 100}%`,
    width: `${el.box.w * 100}%`,
    height: `${el.box.h * 100}%`,
    animationDelay: play && el.anim?.delay ? `${el.anim.delay}s` : undefined,
  };
  const click = onSelect
    ? (e: MouseEvent) => {
        e.stopPropagation();
        onSelect(el.id);
      }
    : undefined;
  const cls = `slide-el${anim}${selected ? " selected" : ""}${onSelect ? " tappable" : ""}`;

  if (el.type === "text") {
    const s = el.style ?? {};
    const head = el.role === "title" || el.role === "number";
    return (
      <div
        className={`${cls} slide-text`}
        style={{
          ...style,
          fontSize: `calc(${s.size ?? 24} * var(--pt))`,
          fontWeight: s.weight ?? (head ? 700 : 400),
          textAlign: s.align ?? "left",
          color: color(s.color, theme.palette.fg),
          fontStyle: s.italic ? "italic" : undefined,
          fontFamily: head ? `"${theme.fonts.head}", system-ui, sans-serif` : undefined,
        }}
        onClick={click}
      >
        {el.text}
      </div>
    );
  }
  if (el.type === "image") {
    return (
      <div className={`${cls} slide-img`} style={style} onClick={click}>
        {src ? <img src={src} alt="" style={{ objectFit: el.fit ?? "cover" }} draggable={false} /> : <span className="slide-img-empty" />}
      </div>
    );
  }
  if (el.type === "chart" && el.chart) {
    return (
      <div className={`${cls} slide-chart`} style={style} onClick={click}>
        <Chart chart={el.chart} theme={theme} />
      </div>
    );
  }
  if (el.type === "shape") {
    return (
      <div
        className={`${cls} slide-shape shape-${el.shape ?? "rect"}`}
        style={{ ...style, background: color(el.fill, theme.palette.accent) }}
        onClick={click}
      />
    );
  }
  return <div className={cls} style={style} onClick={click} />;
}

function Chart({ chart, theme }: { chart: NonNullable<DeckElement["chart"]>; theme: DeckTheme }) {
  const values = chart.series[0]?.values ?? [];
  const max = Math.max(1, ...values);
  const colors = [theme.palette.accent, theme.palette.fg, theme.palette.muted];
  if (chart.kind === "pie" || chart.kind === "donut") {
    const total = values.reduce((a, b) => a + b, 0) || 1;
    let acc = 0;
    return (
      <svg viewBox="-1 -1 2 2" className="chart-svg">
        {values.map((v, i) => {
          const a0 = (acc / total) * Math.PI * 2;
          acc += v;
          const a1 = (acc / total) * Math.PI * 2;
          const large = a1 - a0 > Math.PI ? 1 : 0;
          const d = `M0 0 L${Math.sin(a0)} ${-Math.cos(a0)} A1 1 0 ${large} 1 ${Math.sin(a1)} ${-Math.cos(a1)} Z`;
          return <path key={i} d={d} fill={colors[i % colors.length]} opacity={1 - (i % 3) * 0.15} />;
        })}
        {chart.kind === "donut" && <circle r={0.55} fill="var(--slide-bg, #000)" />}
      </svg>
    );
  }
  const n = Math.max(values.length, 1);
  if (chart.kind === "line") {
    const pts = values.map((v, i) => `${(i / Math.max(n - 1, 1)) * 100},${100 - (v / max) * 90}`).join(" ");
    return (
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="chart-svg">
        <polyline points={pts} fill="none" stroke={theme.palette.accent} strokeWidth={3} vectorEffect="non-scaling-stroke" className="chart-line" />
      </svg>
    );
  }
  return (
    <div className="chart-bars">
      {values.map((v, i) => (
        <div key={i} className="chart-bar">
          <div className="chart-track">
            <span className="chart-val">{v}</span>
            <i className="chart-fill" style={{ height: `${(v / max) * 100}%`, background: theme.palette.accent }} />
          </div>
          <span className="chart-label" style={{ color: theme.palette.muted }}>
            {chart.labels[i]}
          </span>
        </div>
      ))}
    </div>
  );
}
