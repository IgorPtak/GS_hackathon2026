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

  return (
    <ToastContext value={api}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-6 z-[60] flex flex-col items-center gap-2 px-4"
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
