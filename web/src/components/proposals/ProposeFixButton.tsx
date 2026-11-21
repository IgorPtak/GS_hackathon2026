import { useState } from "react";

import type { Alert } from "../../api/types";
import { Button } from "../ui/Button";
import { useToast } from "../ui/toastContext";
import { ProposeFixDialog } from "./ProposeFixDialog";

interface ProposeFixButtonProps {
  readonly alert: Pick<Alert, "id" | "rule_id" | "team" | "runbook_id">;
  readonly className?: string;
}

/** "Propose a fix" button that opens the kit Dialog and confirms via Toast. */
export function ProposeFixButton({ alert, className }: ProposeFixButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const toast = useToast();

  return (
    <>
      <Button
        variant="secondary"
        onClick={() => {
          setIsOpen(true);
        }}
        className={className}
      >
        Propose a fix
      </Button>
      {isOpen ? (
        <ProposeFixDialog
          alert={alert}
          onClose={() => {
            setIsOpen(false);
          }}
          onCreated={() => {
            setIsOpen(false);
            toast.show("Fix proposal sent for review", "success");
          }}
        />
      ) : null}
    </>
  );
}
