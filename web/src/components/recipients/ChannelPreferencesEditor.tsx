import { useState } from "react";

import { apiClient } from "../../api/client";
import type { ConfigValidationError, Recipient } from "../../api/types";
import { detailsFromBody, messageFromBody } from "../rules/ruleErrors";
import { Button } from "../ui/Button";
import { StatusChip } from "../ui/StatusChip";
import { PreferenceRow } from "./PreferenceRow";
import {
  emptyDraft,
  fromDraft,
  toDraft,
  type ChannelPreference,
  type PreferenceDraft,
} from "./preferenceDraft";

interface ChannelPreferencesEditorProps {
  readonly recipient: Recipient;
  readonly team: string;
  readonly channelIds: readonly string[];
  readonly sourceIds: readonly string[];
  readonly onSaved: () => void;
  readonly onClose: () => void;
}

type Outcome = "saved" | "unchanged" | null;

function serialize(preferences: readonly ChannelPreference[]): string {
  return JSON.stringify(preferences);
}

/** Edits the channel preferences of one recipient and saves them with PUT. */
export function ChannelPreferencesEditor({
  recipient,
  team,
  channelIds,
  sourceIds,
  onSaved,
  onClose,
}: ChannelPreferencesEditorProps) {
  const original = recipient.channel_preferences ?? [];
  const [drafts, setDrafts] = useState<PreferenceDraft[]>(original.map(toDraft));
  const [isSaving, setIsSaving] = useState(false);
  const [errors, setErrors] = useState<ConfigValidationError[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome>(null);

  const isChanged =
    serialize(drafts.map(fromDraft)) !== serialize(original.map(toDraft).map(fromDraft));

  function edit(next: PreferenceDraft[]) {
    setDrafts(next);
    setErrors([]);
    setMessage(null);
    setOutcome(null);
  }

  async function handleSave() {
    setIsSaving(true);
    setErrors([]);
    setMessage(null);
    setOutcome(null);
    try {
      const { data, error } = await apiClient.PUT(
        "/api/v1/recipients/{recipient_id}/channel-preferences",
        {
          params: { path: { recipient_id: recipient.id } },
          body: {
            channel_preferences: drafts.map(fromDraft),
            actor: { id: `${team}-operator`, display_name: null },
          },
        },
      );
      if (data) {
        setOutcome(isChanged ? "saved" : "unchanged");
        onSaved();
      } else {
        const details = detailsFromBody(error);
        setErrors(details);
        setMessage(
          details.length > 0
            ? "Some fields need attention. Fix them above, then save again."
            : messageFromBody(error, "Your changes could not be saved. Try again."),
        );
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "API unreachable");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="space-y-5">
      {drafts.length === 0 ? (
        <p className="text-body text-ink-2">
          No preferences yet. This person is reached by each rule's default channels.
        </p>
      ) : null}
      <ul className="space-y-4">
        {drafts.map((draft, index) => (
          <PreferenceRow
            key={index}
            index={index}
            draft={draft}
            channelIds={channelIds}
            sourceIds={sourceIds}
            errors={errors}
            onChange={(next) => {
              edit(drafts.map((d, i) => (i === index ? next : d)));
            }}
            onRemove={() => {
              edit(drafts.filter((_, i) => i !== index));
            }}
          />
        ))}
      </ul>
      {message ? (
        <p
          role="alert"
          className="rounded-tile bg-critical/12 px-4 py-3 text-body text-critical-ink"
        >
          {message}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          isLoading={isSaving}
          onClick={() => {
            void handleSave();
          }}
        >
          Save
        </Button>
        <Button
          icon="plus"
          onClick={() => {
            edit([...drafts, emptyDraft(channelIds[0])]);
          }}
        >
          Add preference
        </Button>
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
        <span aria-live="polite" className="ml-1">
          {outcome === "saved" ? (
            <StatusChip tone="success" icon="check">
              Saved
            </StatusChip>
          ) : null}
          {outcome === "unchanged" ? <StatusChip>Nothing changed</StatusChip> : null}
          {isChanged && outcome === null ? (
            <StatusChip tone="warning">Unsaved changes</StatusChip>
          ) : null}
        </span>
      </div>
    </div>
  );
}
