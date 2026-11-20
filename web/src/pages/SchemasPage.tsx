import { RecentEventsPanel } from "../components/events/RecentEventsPanel";
import { SchemaOnboarding } from "../components/schemas/SchemaOnboarding";
import type { TabId } from "../lib/tabs";

interface SchemasPageProps {
  readonly teamId: string | null;
  readonly onNavigate: (tab: TabId) => void;
}

/** Schemas tab: unknown-schema inbox, mapping form with live test, saved profiles. */
export function SchemasPage({ teamId, onNavigate }: SchemasPageProps) {
  return (
    <section aria-labelledby="schemas-title">
      <h2 id="schemas-title" className="mb-3 text-xl font-semibold">
        Schemas
      </h2>
      <SchemaOnboarding
        teamId={teamId}
        onCreateRule={() => {
          onNavigate("rules");
        }}
      />
      <details className="mt-6 rounded border border-slate-200 bg-white p-3">
        <summary className="cursor-pointer text-sm font-semibold">Recent events</summary>
        <div className="mt-3">
          <RecentEventsPanel />
        </div>
      </details>
    </section>
  );
}
