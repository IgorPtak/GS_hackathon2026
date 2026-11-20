interface WorkingHoursInputProps {
  readonly startTime: string;
  readonly endTime: string;
  readonly timezone: string;
  readonly onChange: (next: { startTime: string; endTime: string; timezone: string }) => void;
  readonly hoursErrors: readonly string[];
  readonly timezoneErrors: readonly string[];
}

const inputClass = "rounded border border-slate-300 px-2 py-1 text-sm";

/** Working hours as HH:MM start/end plus an IANA timezone; empty hours mean "always". */
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
    <fieldset>
      <legend className="text-xs font-medium text-slate-600">Working hours</legend>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <input
          type="time"
          aria-label="Working hours start"
          value={startTime}
          onChange={(e) => {
            onChange({ ...current, startTime: e.target.value });
          }}
          className={inputClass}
        />
        <span className="text-xs text-slate-500">to</span>
        <input
          type="time"
          aria-label="Working hours end"
          value={endTime}
          onChange={(e) => {
            onChange({ ...current, endTime: e.target.value });
          }}
          className={inputClass}
        />
        <input
          type="text"
          aria-label="Timezone"
          value={timezone}
          onChange={(e) => {
            onChange({ ...current, timezone: e.target.value });
          }}
          className={`${inputClass} w-44`}
        />
      </div>
      {[...hoursErrors, ...timezoneErrors].map((message) => (
        <p key={message} role="alert" className="mt-1 text-xs text-red-700">
          {message}
        </p>
      ))}
    </fieldset>
  );
}
