import { useEffect, useId, useRef, type MouseEvent, type ReactNode } from "react";

import { Icon } from "./icons";

interface DialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly title: string;
  readonly footer?: ReactNode;
  readonly children: ReactNode;
}

/** Native modal <dialog>: browser-managed focus, Esc and inert page; click outside dismisses. */
export function Dialog({ isOpen, onClose, title, footer, children }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (isOpen && !dialog.open) dialog.showModal();
    if (!isOpen && dialog.open) dialog.close();
  }, [isOpen]);

  function handleBackdropClick(event: MouseEvent<HTMLDialogElement>) {
    // The backdrop is part of the dialog box, so only clicks on the element itself count.
    if (event.target === event.currentTarget) event.currentTarget.close();
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={handleBackdropClick}
      className="m-auto w-[min(32rem,calc(100vw-2rem))] animate-pop rounded-card border border-hairline bg-card p-0 text-ink shadow-window"
    >
      <div className="flex items-center justify-between gap-4 px-6 pt-5">
        <h2 id={titleId} className="text-card-title font-semibold">
          {title}
        </h2>
        <button
          type="button"
          aria-label="Close"
          onClick={() => {
            ref.current?.close();
          }}
          className="flex size-9 items-center justify-center rounded-full text-ink-2 hover:bg-fill hover:text-ink"
        >
          <Icon name="cross" size={18} />
        </button>
      </div>
      <div className="px-6 py-4">{children}</div>
      {footer ? <div className="flex justify-end gap-2 px-6 pb-5">{footer}</div> : null}
    </dialog>
  );
}
