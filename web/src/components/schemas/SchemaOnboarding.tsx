import { useState } from "react";

import { useEventStream } from "../../hooks/useEventStream";
import { SchemaDraftEditor } from "./SchemaDraftEditor";
import { SchemaProfileList } from "./SchemaProfileList";
import { UnknownSchemaInbox } from "./UnknownSchemaInbox";
import type { SampleEvent } from "./schemaDraft";
import { useSchemaProfiles, useUnknownSchemas } from "./useSchemaLists";

interface SchemaOnboardingProps {
  readonly teamId: string | null;
  readonly onCreateRule: () => void;
}

interface Picked {
  readonly sample: SampleEvent;
  readonly label: string;
  readonly nonce: number;
}

/** Inbox -> mapping form -> test -> save, with the saved profiles listed below. */
export function SchemaOnboarding({ teamId, onCreateRule }: SchemaOnboardingProps) {
  const [picked, setPicked] = useState<Picked | null>(null);
  const inbox = useUnknownSchemas();
  const profiles = useSchemaProfiles();
  useEventStream(teamId, {
    "unknown_schema.detected": inbox.reload,
    "config.changed": profiles.reload,
    onReconnect: () => {
      inbox.reload();
      profiles.reload();
    },
  });

  return (
    <div className="space-y-6">
      <UnknownSchemaInbox
        samples={inbox.items}
        isLoading={inbox.isLoading}
        error={inbox.error}
        onPick={(sample, label) => {
          setPicked((p) => ({ sample, label, nonce: (p?.nonce ?? 0) + 1 }));
        }}
      />
      {picked ? (
        <SchemaDraftEditor
          key={picked.nonce}
          sample={picked.sample}
          label={picked.label}
          team={teamId}
          onClose={() => {
            setPicked(null);
          }}
          onSaved={() => {
            setPicked(null);
            profiles.reload();
            inbox.reload();
          }}
          onCreateRule={onCreateRule}
        />
      ) : null}
      <SchemaProfileList
        profiles={profiles.items}
        isLoading={profiles.isLoading}
        error={profiles.error}
      />
    </div>
  );
}
