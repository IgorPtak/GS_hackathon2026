import { useState } from "react";

import type { Recipient } from "../../api/types";
import { PersonAvatar } from "./PersonAvatar";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { ChannelPreferencesEditor } from "./ChannelPreferencesEditor";
import { describePreference } from "./preferenceSentence";

interface PersonCardProps {
  readonly recipient: Recipient;
  readonly team: string;
  readonly channelIds: readonly string[];
  readonly sourceIds: readonly string[];
  readonly onSaved: () => void;
}

/** One person: avatar, teams, their channel preferences as sentences, and an Edit button. */
export function PersonCard({ recipient, team, channelIds, sourceIds, onSaved }: PersonCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const preferences = recipient.channel_preferences ?? [];
  const teams = recipient.teams ?? [];
  return (
    <Card as="li" className="space-y-5">
      <div className="flex items-start gap-4">
        <PersonAvatar name={recipient.display_name} team={teams[0] ?? team} />
        <div className="min-w-0 flex-1">
          <h3 className="text-row font-semibold">{recipient.display_name}</h3>
          <p className="text-meta text-ink-2">{teams.length > 0 ? teams.join(", ") : "No team"}</p>
        </div>
        {isEditing ? null : (
          <Button
            onClick={() => {
              setIsEditing(true);
            }}
          >
            Edit
          </Button>
        )}
      </div>
      {isEditing ? (
        <ChannelPreferencesEditor
          recipient={recipient}
          team={team}
          channelIds={channelIds}
          sourceIds={sourceIds}
          onSaved={onSaved}
          onClose={() => {
            setIsEditing(false);
          }}
        />
      ) : preferences.length === 0 ? (
        <p className="text-body text-ink-2">
          No personal preferences. This person gets each rule's default channels.
        </p>
      ) : (
        <ul className="space-y-2">
          {preferences.map((preference, index) => (
            <li key={index} className="rounded-tile bg-panel px-4 py-3 text-body">
              {describePreference(preference)}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
