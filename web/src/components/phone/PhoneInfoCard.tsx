import type { Recipient } from "../../api/types";
import type { StreamStatus } from "../../hooks/useEventStream";
import { Avatar } from "../ui/Avatar";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Field } from "../ui/Field";
import { Icon } from "../ui/icons";
import { Select, type SelectOption } from "../ui/Select";
import { StatusChip, type ChipTone } from "../ui/StatusChip";
import type { SpeechController } from "./useSpeech";
import { formatVoiceLabel } from "./voiceSelection";

interface PhoneInfoCardProps {
  readonly recipients: readonly Recipient[];
  readonly selectedRecipient: Recipient | null;
  readonly onSelectRecipient: (id: string) => void;
  readonly streamStatus: StreamStatus;
  readonly speech: SpeechController;
}

const STREAM_BADGE: Record<StreamStatus, { readonly label: string; readonly tone: ChipTone }> = {
  open: { label: "Live", tone: "success" },
  connecting: { label: "Connecting", tone: "warning" },
  retrying: { label: "Reconnecting", tone: "critical" },
  idle: { label: "Offline", tone: "neutral" },
};

/** Quiet side card beside the device frame in the shell: explanation, recipient pill, voice picker. */
export function PhoneInfoCard({
  recipients,
  selectedRecipient,
  onSelectRecipient,
  streamStatus,
  speech,
}: PhoneInfoCardProps) {
  const firstName = selectedRecipient?.display_name.trim().split(/\s+/)[0] ?? "Piotr";
  const badge = STREAM_BADGE[streamStatus];
  const voiceOptions: SelectOption[] = [
    {
      value: "",
      label: speech.activeVoice
        ? `Automatic (${speech.activeVoice.name})`
        : "Automatic (best voice)",
    },
    ...speech.voices.map((voice) => ({
      value: voice.voiceURI,
      label: formatVoiceLabel(voice),
    })),
  ];

  function previewVoice() {
    speech.speakSentences([
      `Hi ${firstName}.`,
      "This is Beacon.",
      "To approve, enter code:",
      "four.",
      "six.",
      "zero.",
      "two.",
    ]);
  }

  return (
    <Card className="flex w-full max-w-[348px] flex-col gap-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <Avatar
            name={selectedRecipient?.display_name ?? "Piotr Nowak"}
            team={selectedRecipient?.teams?.[0]}
            size="md"
          />
          <div className="min-w-0">
            <p className="truncate text-row font-semibold text-ink">
              {selectedRecipient?.display_name ?? "Phone"}
            </p>
            <p className="truncate text-meta text-ink-2">
              {selectedRecipient?.contacts?.phone ?? "On-call device"}
            </p>
          </div>
        </div>
        <StatusChip tone={badge.tone}>{badge.label}</StatusChip>
      </div>

      <p className="text-body text-ink-2">
        This simulates {firstName}&apos;s phone. Calls and texts arrive here.
      </p>

      {recipients.length > 0 && selectedRecipient ? (
        <div className="flex flex-col gap-1.5">
          <label htmlFor="phone-recipient-select" className="text-meta font-medium text-ink">
            Recipient
          </label>
          <span className="relative inline-flex w-fit max-w-full items-center">
            <select
              id="phone-recipient-select"
              value={selectedRecipient.id}
              onChange={(event) => {
                onSelectRecipient(event.target.value);
              }}
              className="h-9 max-w-full appearance-none rounded-full border border-hairline bg-fill pr-9 pl-4 text-body font-medium text-ink transition-colors hover:bg-hairline"
            >
              {recipients.map((recipient) => (
                <option key={recipient.id} value={recipient.id}>
                  {recipient.display_name}
                </option>
              ))}
            </select>
            <Icon
              name="chevron"
              size={15}
              className="pointer-events-none absolute right-3 text-ink-2"
            />
          </span>
        </div>
      ) : null}

      {speech.isSupported ? (
        <div className="flex flex-col gap-2.5 border-t border-hairline pt-4">
          <Field label="Voice">
            {(control) => (
              <Select
                {...control}
                value={speech.selectedVoiceUri}
                options={voiceOptions}
                onChange={speech.setSelectedVoiceUri}
              />
            )}
          </Field>
          <div>
            <Button variant="secondary" size="md" icon="volume" onClick={previewVoice}>
              Test voice
            </Button>
          </div>
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-3 border-t border-hairline pt-4 text-meta text-ink-2">
        <span>Open on a real phone</span>
        <a
          href="/phone"
          className="inline-flex items-center gap-1 font-medium text-accent-ink hover:underline"
        >
          Full screen
          <Icon name="external" size={14} />
        </a>
      </div>
    </Card>
  );
}
