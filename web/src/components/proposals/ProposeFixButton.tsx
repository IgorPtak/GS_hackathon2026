import { useEffect, useState } from "react";

import type { Alert } from "../../api/types";
import { ProposeFixDialog } from "./ProposeFixDialog";

interface ProposeFixButtonProps {
  readonly alert: Pick<Alert, "id" | "rule_id" | "team" | "runbook_id">;
  readonly className?: string;
}

/** "Propose a fix" button that owns its dialog and a success toast with the proposal id. */
export function ProposeFixButton({ alert, className }: ProposeFixButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [createdId, setCreatedId] = useState<string | null>(null);

  useEffect(() => {
    if (createdId === null) return;
    const timer = window.setTimeout(() => {
      setCreatedId(null);
    }, 6000);
    return () => {
      window.clearTimeout(timer);
    };
  }, [createdId]);

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setIsOpen(true);
        }}
        className={
          className ??
          "rounded border border-slate-300 px-2 py-1 text-xs whitespace-nowrap hover:bg-slate-50"
        }
      >
        Propose a fix
      </button>
      {isOpen ? (
        <ProposeFixDialog
          alert={alert}
          onClose={() => {
            setIsOpen(false);
          }}
          onCreated={(proposal) => {
            setIsOpen(false);
            setCreatedId(proposal.id);
          }}
        />
      ) : null}
      {createdId !== null ? (
        <div
          role="status"
          className="fixed right-4 bottom-4 z-40 max-w-sm rounded bg-green-700 px-4 py-2 text-sm text-white shadow-lg"
        >
          Fix proposal sent: <span className="font-mono break-all">{createdId}</span>
        </div>
      ) : null}
    </>
  );
}
