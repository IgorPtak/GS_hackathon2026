import { useState } from "react";

import { RecentEventsPanel } from "../components/events/RecentEventsPanel";
import { Icon } from "../components/ui/icons";
import { SchemaOnboarding } from "../components/schemas/SchemaOnboarding";
import type { TabId } from "../lib/tabs";

interface SchemasPageProps {
  readonly teamId: string | null;
  readonly onNavigate: (tab: TabId) => void;
}

/** Connect a system: the 3-step mapping flow, with the raw recent events under "Advanced". */
export function SchemasPage({ teamId, onNavigate }: SchemasPageProps) {
  const [isRecentOpen, setIsRecentOpen] = useState(false);
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <SchemaOnboarding
        teamId={teamId}
        onCreateRule={() => {
          onNavigate("rules");
        }}
      />
      <details
        className="group rounded-card border border-hairline bg-card px-6 py-4"
        onToggle={(e) => {
          setIsRecentOpen(e.currentTarget.open);
        }}
      >
        <summary className="flex cursor-pointer list-none items-center gap-2 text-body font-semibold">
          <Icon
            name="chevron"
            size={16}
            className="-rotate-90 transition-transform group-open:rotate-0"
          />
          <span className="whitespace-nowrap">Recent events</span>
          <span className="text-meta font-normal text-ink-2 max-sm:hidden">
            as Beacon received them
          </span>
        </summary>
        <div className="mt-4">{isRecentOpen ? <RecentEventsPanel /> : null}</div>
      </details>
    </div>
  );
}
