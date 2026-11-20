import { useState } from "react";

import { apiClient } from "../../api/client";
import type { ConfigValidationError, Recipient } from "../../api/types";
import { detailsFromBody, messageFromBody } from "../rules/ruleErrors";
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
        setErrors(detailsFromBody(error));
        setMessage(messageFromBody(error, "Save failed"));
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "API unreachable");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="space-y-3 rounded border border-slate-200 bg-slate-50 p-3">
      <h4 className="font-semibold">
        {recipient.display_name}{" "}
        <span className="text-xs font-normal text-slate-500">{recipient.id}</span>
      </h4>
      {drafts.length === 0 ? (
        <p className="text-sm text-slate-500">No preferences: the default channels are used.</p>
      ) : null}
      <ul className="space-y-2">
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
        <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          {message}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => {
            edit([...drafts, emptyDraft(channelIds[0])]);
          }}
          className="rounded border border-slate-300 bg-white px-3 py-1 text-sm hover:bg-slate-50"
        >
          Add preference
        </button>
        <button
          type="button"
          disabled={isSaving}
          onClick={() => {
            void handleSave();
          }}
          className="rounded bg-slate-800 px-3 py-1 text-sm text-white disabled:opacity-50"
        >
          {isSaving ? "Saving..." : "Save preferences"}
        </button>
        {outcome === "saved" ? <span className="text-sm text-green-700">Saved</span> : null}
        {outcome === "unchanged" ? (
          <span className="text-sm text-slate-600">Unchanged, nothing saved</span>
        ) : null}
        {isChanged && outcome === null ? (
          <span className="text-xs text-amber-700">Unsaved changes</span>
        ) : null}
      </div>
    </div>
  );
}
