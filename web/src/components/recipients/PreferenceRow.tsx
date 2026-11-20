import type { ConfigValidationError } from "../../api/types";
import { ChipSelect } from "./ChipSelect";
import { WorkingHoursInput } from "./WorkingHoursInput";
import { SEVERITIES, errorsAt, type PreferenceDraft } from "./preferenceDraft";

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
  const messages = (field: string) => errorsAt(errors, index, field).map((e) => e.message);
  return (
    <li className="space-y-3 rounded border border-slate-200 bg-white p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-500">Preference {index + 1}</span>
        <button type="button" onClick={onRemove} className="text-xs text-red-700 hover:underline">
          Remove
        </button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <ChipSelect
          label="Severities"
          options={SEVERITIES}
          selected={draft.severities}
          hint="None selected = any severity"
          errors={messages("when.severities")}
          onChange={(next) => {
            onChange({ ...draft, severities: next as PreferenceDraft["severities"] });
          }}
        />
        <ChipSelect
          label="Sources"
          options={sourceIds}
          selected={draft.sources}
          hint="None selected = any source"
          errors={messages("when.sources")}
          onChange={(next) => {
            onChange({ ...draft, sources: next });
          }}
        />
        <ChipSelect
          label="Channels"
          options={channelIds}
          selected={draft.channels}
          errors={messages("channels")}
          onChange={(next) => {
            onChange({ ...draft, channels: next });
          }}
        />
        <ChipSelect
          label="Otherwise (outside working hours)"
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
        hoursErrors={messages("working_hours")}
        timezoneErrors={messages("timezone")}
        onChange={(next) => {
          onChange({ ...draft, ...next });
        }}
      />
    </li>
  );
}
