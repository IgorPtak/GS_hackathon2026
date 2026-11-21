import { useEffect, useId, useRef, type MouseEvent, type ReactNode } from "react";

import { cx } from "../../lib/cx";
import { Icon } from "./icons";

interface DialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly title: string;
  /** Quiet line under the title. */
  readonly subtitle?: ReactNode;
  readonly footer?: ReactNode;
  /** `sheet` slides in from the right and fills the height (tools, consoles). */
  readonly variant?: "modal" | "sheet";
  readonly width?: "md" | "lg";
  readonly children: ReactNode;
}

/**
 * Native modal <dialog>: browser-managed focus, Esc and inert page; click outside dismisses.
 * Only the body scrolls, and it keeps its own padding, so focus rings are never clipped.
 */
export function Dialog({
  isOpen,
  onClose,
  title,
  subtitle,
  footer,
  variant = "modal",
  width = "md",
  children,
}: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (isOpen && !dialog.open) {
      dialog.showModal();
      // The dialog itself takes focus (not the close button), so no stray focus ring on open;
      // Tab still moves straight into the content.
      dialog.focus();
    }
    if (!isOpen && dialog.open) dialog.close();
  }, [isOpen]);

  function handleBackdropClick(event: MouseEvent<HTMLDialogElement>) {
    // The backdrop is part of the dialog box, so only clicks on the element itself count.
    if (event.target === event.currentTarget) event.currentTarget.close();
  }

  const isSheet = variant === "sheet";
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      tabIndex={-1}
      onClose={onClose}
      onClick={handleBackdropClick}
      className={cx(
        "modal-dialog flex-col border border-hairline bg-card p-0 text-ink shadow-window outline-none open:flex",
        isSheet
          ? "sheet-dialog my-3 mr-3 ml-auto h-[calc(100dvh-1.5rem)] max-h-none w-[min(1120px,calc(100vw-1.5rem))] rounded-[24px]"
          : cx(
              "m-auto max-h-[min(86dvh,860px)] rounded-card",
              width === "lg"
                ? "w-[min(44rem,calc(100vw-2rem))]"
                : "w-[min(34rem,calc(100vw-2rem))]",
            ),
      )}
    >
      <div
        className={cx(
          "flex shrink-0 items-start justify-between gap-4 px-7 pt-6 pb-2",
          isSheet && "pb-4",
        )}
      >
        <div className="min-w-0">
          <h2 id={titleId} className="text-card-title font-semibold tracking-tight">
            {title}
          </h2>
          {subtitle ? <div className="mt-0.5 text-meta text-ink-2">{subtitle}</div> : null}
        </div>
        <button
          type="button"
          aria-label="Close"
          onClick={() => {
            ref.current?.close();
          }}
          className="-mr-2 flex size-9 shrink-0 items-center justify-center rounded-full text-ink-2 transition-colors hover:bg-fill hover:text-ink active:scale-95"
        >
          <Icon name="cross" size={18} />
        </button>
      </div>
      <div
        className={cx(
          "min-h-0 flex-1 overflow-y-auto overscroll-contain px-7 py-4 [scrollbar-gutter:stable]",
          isSheet && "pt-1",
        )}
      >
        {children}
      </div>
      {footer ? (
        <div className="flex shrink-0 items-center justify-end gap-2 border-t border-hairline px-7 py-4">
          {footer}
        </div>
      ) : null}
    </dialog>
  );
}
