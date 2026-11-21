import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { cx } from "../../lib/cx";
import { Icon } from "./icons";
import { ToastContext, type ToastApi, type ToastTone } from "./toastContext";

interface ToastItem {
  readonly id: number;
  readonly message: string;
  readonly tone: ToastTone;
}

const LIFETIME_MS: Record<ToastTone, number> = { success: 4000, info: 4000, error: 8000 };

/** Provides `useToast()` and renders the persistent polite live region. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<readonly ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Set<number>());

  useEffect(() => {
    const active = timers.current;
    return () => {
      active.forEach((timer) => {
        window.clearTimeout(timer);
      });
    };
  }, []);

  const show = useCallback((message: string, tone: ToastTone = "success") => {
    const id = nextId.current++;
    setToasts((current) => [...current.slice(-3), { id, message, tone }]);
    const timer = window.setTimeout(() => {
      timers.current.delete(timer);
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, LIFETIME_MS[tone]);
    timers.current.add(timer);
  }, []);

  const api = useMemo<ToastApi>(() => ({ show }), [show]);

  // Toasts live in a manual popover so they sit above an open modal dialog (top layer). Re-showing
  // it on each toast moves it to the top of that layer, above a dialog opened since.
  const region = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = region.current;
    if (!element || !("showPopover" in element)) return;
    if (element.matches(":popover-open")) element.hidePopover();
    if (toasts.length > 0) element.showPopover();
  }, [toasts]);

  return (
    <ToastContext value={api}>
      {children}
      <div
        ref={region}
        popover="manual"
        role="status"
        aria-live="polite"
        style={{ inset: "auto 0 24px 0" }}
        className="pointer-events-none fixed z-[60] m-0 flex h-auto w-full flex-col items-center gap-2 overflow-visible border-0 bg-transparent p-0 px-4 text-ink [&:not(:popover-open)]:hidden"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className="pointer-events-auto flex animate-pop items-center gap-2.5 rounded-full border border-hairline bg-card py-2 pr-4 pl-3 text-body font-medium shadow-window"
          >
            <Icon
              name={toast.tone === "error" ? "alert" : "check"}
              size={18}
              className={cx(
                toast.tone === "error" && "text-critical-ink",
                toast.tone === "success" && "text-success-ink",
                toast.tone === "info" && "text-accent-ink",
              )}
            />
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext>
  );
}
