import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

import { haptic, tg } from "../lib/tg";

/** Главная кнопка экрана. В Telegram — нативная MainButton, в браузере — кнопка внизу. */
export function MainButton({
  text,
  onClick,
  disabled = false,
  loading = false,
}: {
  text: string;
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
}) {
  const handler = useRef(onClick);
  handler.current = onClick;

  useEffect(() => {
    if (!tg) return;
    const mb = tg.MainButton;
    const click = () => {
      haptic.tap();
      handler.current();
    };
    mb.onClick(click);
    return () => {
      mb.offClick(click);
      mb.setParams({ is_visible: false });
    };
  }, []);

  useEffect(() => {
    if (!tg) return;
    const css = getComputedStyle(document.documentElement);
    tg.MainButton.setParams({
      text,
      is_visible: true,
      is_active: !disabled && !loading,
      color: disabled ? "#8E8E93" : css.getPropertyValue("--accent").trim(),
      text_color: disabled ? "#FFFFFF" : css.getPropertyValue("--on-accent").trim(),
    });
    if (loading) tg.MainButton.showProgress(false);
    else tg.MainButton.hideProgress();
  }, [text, disabled, loading]);

  if (tg) return null;
  return createPortal(
    <div className="bottom-bar">
      <button className="btn btn-filled" disabled={disabled || loading} onClick={onClick}>
        {loading ? "…" : text}
      </button>
    </div>,
    document.body,
  );
}

/** Нативная кнопка «Назад» Telegram. */
export function BackButton({ onClick }: { onClick: () => void }) {
  const handler = useRef(onClick);
  handler.current = onClick;
  useEffect(() => {
    if (!tg) return;
    const click = () => handler.current();
    tg.BackButton.onClick(click);
    tg.BackButton.show();
    return () => {
      tg?.BackButton.offClick(click);
      tg?.BackButton.hide();
    };
  }, []);
  return null;
}
