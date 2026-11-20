import { useState } from "react";

import { NEW_RULE, RulesPage, type RulesSelection } from "../pages/RulesPage";
import { Button } from "../components/ui/Button";
import { PageFrame } from "../components/ui/PageFrame";
import type { ScreenProps } from "./types";

/** Rules screen: the team's rules as cards; opening one starts the 3-step flow. */
export function RulesScreen({ teamId, teamLabel }: ScreenProps) {
  const [selection, setSelection] = useState<RulesSelection>(null);
  return (
    <PageFrame
      title="Rules"
      context={teamLabel}
      actions={
        <Button
          variant="primary"
          icon="plus"
          onClick={() => {
            setSelection(NEW_RULE);
          }}
        >
          New rule
        </Button>
      }
    >
      <RulesPage key={teamId} teamId={teamId} selection={selection} onSelect={setSelection} />
    </PageFrame>
  );
}
