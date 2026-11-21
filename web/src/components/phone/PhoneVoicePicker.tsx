import { Button } from "../ui/Button";
import { Field } from "../ui/Field";
import { Select, type SelectOption } from "../ui/Select";
import type { SpeechController } from "./useSpeech";
import { formatVoiceLabel } from "./voiceSelection";

/** The English voice the phone reads calls with, plus a short sample to hear it. */
export function PhoneVoicePicker({
  speech,
  firstName,
}: {
  readonly speech: SpeechController;
  readonly firstName: string;
}) {
  if (!speech.isSupported) {
    return <p className="text-meta text-ink-2">This browser cannot read calls aloud.</p>;
  }
  const options: SelectOption[] = [
    {
      value: "",
      label: speech.activeVoice
        ? `Automatic · ${formatVoiceLabel(speech.activeVoice)}`
        : "Automatic · best English voice",
    },
    ...speech.voices.map((voice) => ({ value: voice.voiceURI, label: formatVoiceLabel(voice) })),
  ];
  return (
    <div className="flex flex-col gap-2.5">
      <Field label="Voice">
        {(control) => (
          <Select
            {...control}
            value={speech.selectedVoiceUri}
            options={options}
            onChange={speech.setSelectedVoiceUri}
          />
        )}
      </Field>
      <div>
        <Button
          variant="secondary"
          icon="volume"
          onClick={() => {
            speech.speakSentences([
              `Hi ${firstName}.`,
              "This is Beacon.",
              "To approve, enter code:",
              "four. six. zero. two.",
            ]);
          }}
        >
          Test voice
        </Button>
      </div>
    </div>
  );
}
