import { Check, ChevronRight, X } from "lucide-react";
import { useEffect, useRef, useState, type ImgHTMLAttributes, type PointerEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { haptic } from "../lib/tg";

export function Section({
  title,
  action,
  footer,
  large,
  id,
  need,
  children,
}: {
  title?: ReactNode;
  action?: { label: string; onClick: () => void };
  footer?: ReactNode;
  large?: boolean;
  id?: string;
  need?: boolean; // не заполнено обязательное — подсветить
  children: ReactNode;
}) {
  return (
    <section className={`section${need ? " need" : ""}`} id={id}>
      {title && (
        <div className={`section-header${large ? " large" : ""}`}>
          <span>{title}</span>
          {action && <button onClick={action.onClick}>{action.label}</button>}
        </div>
      )}
      {children}
      {footer && <div className="section-footer">{footer}</div>}
    </section>
  );
}

export function Group({ children, icons }: { children: ReactNode; icons?: boolean }) {
  return <div className={`group${icons ? " with-icons" : ""}`}>{children}</div>;
}

export function Cell({
  icon,
  iconBg,
  title,
  subtitle,
  value,
  chevron,
  checked,
  accessory,
  disabled,
  onClick,
}: {
  icon?: ReactNode;
  iconBg?: string;
  title: ReactNode;
  subtitle?: ReactNode;
  value?: ReactNode;
  chevron?: boolean;
  checked?: boolean;
  accessory?: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
}) {
  const content = (
    <>
      {icon && (
        <span className="cell-icon" style={iconBg ? { background: iconBg } : undefined}>
          {icon}
        </span>
      )}
      <span className="cell-body">
        <div className="cell-title">{title}</div>
        {subtitle && <div className="cell-subtitle">{subtitle}</div>}
      </span>
      {value !== undefined && <span className="cell-value">{value}</span>}
      {accessory}
      {checked && <Check className="cell-check" strokeWidth={2.5} />}
      {chevron && <ChevronRight className="cell-chevron" strokeWidth={3} />}
    </>
  );
  if (!onClick) return <div className={`cell${disabled ? " disabled" : ""}`}>{content}</div>;
  return (
    <button
      className={`cell${disabled ? " disabled" : ""}`}
      onClick={() => {
        haptic.select();
        onClick();
      }}
    >
      {content}
    </button>
  );
}

export function Switch({ on }: { on: boolean }) {
  return <span className={`switch${on ? " on" : ""}`} role="switch" aria-checked={on} />;
}

export function ToggleCell({ title, subtitle, on, onChange }: { title: ReactNode; subtitle?: ReactNode; on: boolean; onChange: (v: boolean) => void }) {
  return <Cell title={title} subtitle={subtitle} accessory={<Switch on={on} />} onClick={() => onChange(!on)} />;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T | null;
  onChange: (v: T) => void;
}) {
  return (
    <div className="segmented" role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={o.value === value}
          className={o.value === value ? "on" : ""}
          onClick={() => {
            haptic.select();
            onChange(o.value);
          }}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Chips<T extends string>({ options, value, onChange }: { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="chips">
      {options.map((o) => (
        <button
          key={o.value}
          className={`chip${o.value === value ? " on" : ""}`}
          onClick={() => {
            haptic.select();
            onChange(o.value);
          }}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function TextArea({
  value,
  onChange,
  placeholder,
  maxLength,
  rows = 3,
  label,
  autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  maxLength: number;
  rows?: number;
  label?: string;
  autoFocus?: boolean;
}) {
  return (
    <div className="field-cell">
      {label && <div className="field-label">{label}</div>}
      <textarea
        className="field"
        rows={rows}
        value={value}
        maxLength={maxLength}
        placeholder={placeholder}
        autoFocus={autoFocus}
        onChange={(e) => onChange(e.target.value)}
      />
      {value.length > maxLength * 0.8 && (
        <div className="counter">
          {value.length}/{maxLength}
        </div>
      )}
    </div>
  );
}

export function TextInput({
  value,
  onChange,
  placeholder,
  maxLength,
  label,
  inputMode,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  maxLength: number;
  label?: string;
  inputMode?: "url" | "tel" | "text";
}) {
  return (
    <div className="field-cell">
      {label && <div className="field-label">{label}</div>}
      <input
        className="field"
        value={value}
        maxLength={maxLength}
        placeholder={placeholder}
        inputMode={inputMode}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

export function Button({
  children,
  kind = "filled",
  small,
  disabled,
  onClick,
}: {
  children: ReactNode;
  kind?: "filled" | "tinted" | "gray" | "plain";
  small?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={`btn btn-${kind}${small ? " btn-small" : ""}`}
      disabled={disabled}
      onClick={() => {
        haptic.tap();
        onClick();
      }}
    >
      {children}
    </button>
  );
}

export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title?: ReactNode; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);
  if (!open) return null;
  return createPortal(
    <>
      <div className="sheet-backdrop" onClick={onClose} />
      <div className="sheet" role="dialog" aria-modal="true">
        <div className="sheet-grabber" />
        {title && (
          <div className="sheet-head">
            <h2 className="title3">{title}</h2>
            <button className="btn btn-gray btn-small" style={{ width: 30, height: 30, padding: 0 }} onClick={onClose} aria-label="close">
              <X size={16} strokeWidth={2.5} />
            </button>
          </div>
        )}
        {children}
      </div>
    </>,
    document.body,
  );
}

export function Skeleton({ height, width = "100%", radius }: { height: number; width?: number | string; radius?: number }) {
  return <div className="skeleton" style={{ height, width, borderRadius: radius }} />;
}

export function Empty({ icon, title, text, action }: { icon: ReactNode; title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <div className="title3">{title}</div>
      {text && <p className="subhead secondary">{text}</p>}
      {action && <div className="mt-16">{action}</div>}
    </div>
  );
}

export function Toast({ text, onDone }: { text: string | null; onDone: () => void }) {
  useEffect(() => {
    if (!text) return;
    const id = setTimeout(onDone, 2600);
    return () => clearTimeout(id);
  }, [text, onDone]);
  if (!text) return null;
  return createPortal(<div className="toast">{text}</div>, document.body);
}

/** Картинка, которая мягко проявляется после загрузки, а не «выпрыгивает» строками. */
export function Img({ className, ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  const ref = useRef<HTMLImageElement>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    if (ref.current?.complete) setLoaded(true); // уже из кэша — без анимации-ожидания
  }, []);
  return (
    <img
      ref={ref}
      loading="lazy"
      decoding="async"
      {...props}
      className={`img-fade${loaded ? " loaded" : ""}${className ? ` ${className}` : ""}`}
      onLoad={() => setLoaded(true)}
      onError={() => setLoaded(true)}
    />
  );
}

/** Блик, который следует за пальцем: пишет координаты в CSS-переменные --mx/--my не чаще кадра. */
export function useGlare() {
  const frame = useRef(0);
  return (e: PointerEvent<HTMLElement>) => {
    const el = e.currentTarget;
    const { left, top, width, height } = el.getBoundingClientRect();
    const x = ((e.clientX - left) / width) * 100;
    const y = ((e.clientY - top) / height) * 100;
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      el.style.setProperty("--mx", `${30 + x * 0.4}%`);
      el.style.setProperty("--my", `${30 + y * 0.4}%`);
    });
  };
}
