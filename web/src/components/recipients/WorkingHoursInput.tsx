import { Field } from "../ui/Field";
import { Select } from "../ui/Select";
import { TextInput } from "../ui/TextInput";

interface WorkingHoursInputProps {
  readonly startTime: string;
  readonly endTime: string;
  readonly timezone: string;
  readonly onChange: (next: { startTime: string; endTime: string; timezone: string }) => void;
  readonly hoursErrors: readonly string[];
  readonly timezoneErrors: readonly string[];
}

const FALLBACK_ZONES = [
  "Europe/Warsaw",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "UTC",
];

/** Every IANA zone the browser knows, always including the current value so it never vanishes. */
function timezoneOptions(current: string) {
  const known =
    typeof Intl.supportedValuesOf === "function"
      ? Intl.supportedValuesOf("timeZone")
      : FALLBACK_ZONES;
  const zones = known.includes(current) || current === "" ? known : [current, ...known];
  return zones.map((zone) => ({ value: zone, label: zone.replace(/_/g, " ") }));
}

/** Working hours as two time inputs plus a timezone select; empty hours mean "any time". */
export function WorkingHoursInput({
  startTime,
  endTime,
  timezone,
  onChange,
  hoursErrors,
  timezoneErrors,
}: WorkingHoursInputProps) {
  const current = { startTime, endTime, timezone };
  return (
    <div className="grid gap-4 sm:grid-cols-[8rem_8rem_1fr]">
      <Field label="From" error={hoursErrors[0]}>
        {(control) => (
          <TextInput
            {...control}
            type="time"
            value={startTime}
            onChange={(e) => {
              onChange({ ...current, startTime: e.target.value });
            }}
          />
        )}
      </Field>
      <Field label="Until">
        {(control) => (
          <TextInput
            {...control}
            type="time"
            value={endTime}
            onChange={(e) => {
              onChange({ ...current, endTime: e.target.value });
            }}
          />
        )}
      </Field>
      <Field
        label="Timezone"
        help="Working hours. Leave both times empty to apply at any hour."
        error={timezoneErrors[0]}
      >
        {(control) => (
          <Select
            {...control}
            value={timezone}
            options={timezoneOptions(timezone)}
            onChange={(zone) => {
              onChange({ ...current, timezone: zone });
            }}
          />
        )}
      </Field>
    </div>
  );
}
