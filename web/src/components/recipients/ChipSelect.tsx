import { MultiSelect } from "../ui/MultiSelect";
import { channelWord } from "./preferenceSentence";

interface ChipSelectProps {
  readonly label: string;
  readonly options: readonly string[];
  readonly selected: readonly string[];
  readonly onChange: (next: string[]) => void;
  readonly errors: readonly string[];
  readonly hint?: string;
  /** Shows channel ids as plain words ("sms" becomes "SMS"). */
  readonly isChannel?: boolean;
}

/** Multi-select as toggle chips with a visible label, hint and the API error for this field. */
export function ChipSelect({
  label,
  options,
  selected,
  onChange,
  errors,
  hint,
  isChannel = false,
}: ChipSelectProps) {
  return (
    <div className="min-w-0 space-y-2">
      <p className="text-meta font-medium text-ink">{label}</p>
      {options.length === 0 ? (
        <p className="text-meta text-ink-2">None configured.</p>
      ) : (
        <MultiSelect
          label={label}
          options={options.map((option) => ({
            value: option,
            label: isChannel ? channelWord(option) : option,
          }))}
          values={selected}
          onChange={onChange}
        />
      )}
      {hint ? <p className="text-meta text-ink-2">{hint}</p> : null}
      {errors.map((message) => (
        <p key={message} role="alert" className="text-meta text-critical-ink">
          {message}
        </p>
      ))}
    </div>
  );
}
