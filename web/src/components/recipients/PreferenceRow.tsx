import type { ConfigValidationError } from "../../api/types";
import { Button } from "../ui/Button";
import { ChipSelect } from "./ChipSelect";
import { WorkingHoursInput } from "./WorkingHoursInput";
import { SEVERITIES, errorsAt, humanizeError, type PreferenceDraft } from "./preferenceDraft";

interface PreferenceRowProps {
  readonly index: number;
  readonly draft: PreferenceDraft;
  readonly channelIds: readonly string[];
  readonly sourceIds: readonly string[];
  readonly errors: readonly ConfigValidationError[];
  readonly onChange: (next: PreferenceDraft) => void;
  readonly onRemove: () => void;
}

/** One preference: who it matches, where it notifies in working hours and the fallback outside. */
export function PreferenceRow({
  index,
  draft,
  channelIds,
  sourceIds,
  errors,
  onChange,
  onRemove,
}: PreferenceRowProps) {
  const messages = (field: string) =>
    errorsAt(errors, index, field).map((e) => humanizeError(field, e.message));
  const hours = [...messages("working_hours")];
  return (
    <li className="space-y-5 rounded-tile border border-hairline bg-panel p-5">
      <div className="flex items-center justify-between">
        <h4 className="text-body font-semibold">Preference {index + 1}</h4>
        <Button variant="ghost" onClick={onRemove}>
          Remove
        </Button>
      </div>
      <div className="grid gap-5 md:grid-cols-2">
        <ChipSelect
          label="Alert severities"
          options={SEVERITIES}
          selected={draft.severities}
          hint="Nothing selected means any severity."
          errors={messages("when.severities")}
          onChange={(next) => {
            onChange({ ...draft, severities: next as PreferenceDraft["severities"] });
          }}
        />
        <ChipSelect
          label="Systems"
          options={sourceIds}
          selected={draft.sources}
          hint="Nothing selected means any system."
          errors={messages("when.sources")}
          onChange={(next) => {
            onChange({ ...draft, sources: next });
          }}
        />
        <ChipSelect
          label="Send by"
          isChannel
          options={channelIds}
          selected={draft.channels}
          errors={messages("channels")}
          onChange={(next) => {
            onChange({ ...draft, channels: next });
          }}
        />
        <ChipSelect
          label="Outside working hours, send by"
          isChannel
          options={channelIds}
          selected={draft.otherwise}
          errors={messages("otherwise")}
          onChange={(next) => {
            onChange({ ...draft, otherwise: next });
          }}
        />
      </div>
      <WorkingHoursInput
        startTime={draft.startTime}
        endTime={draft.endTime}
        timezone={draft.timezone}
        hoursErrors={hours}
        timezoneErrors={messages("timezone")}
        onChange={(next) => {
          onChange({ ...draft, ...next });
        }}
      />
    </li>
  );
}
