import { toggled } from "./preferenceDraft";

interface ChipSelectProps {
  readonly label: string;
  readonly options: readonly string[];
  readonly selected: readonly string[];
  readonly onChange: (next: string[]) => void;
  readonly errors: readonly string[];
  readonly hint?: string;
}

/** Multi-select as toggle chips; shows the API error for this field underneath. */
export function ChipSelect({ label, options, selected, onChange, errors, hint }: ChipSelectProps) {
  return (
    <fieldset className="min-w-0">
      <legend className="text-xs font-medium text-slate-600">{label}</legend>
      <div className="mt-1 flex flex-wrap gap-1">
        {options.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={selected.includes(option)}
            onClick={() => {
              onChange(toggled(selected, option));
            }}
            className={`rounded-full border px-2 py-0.5 text-xs ${
              selected.includes(option)
                ? "border-slate-800 bg-slate-800 text-white"
                : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
            }`}
          >
            {option}
          </button>
        ))}
        {options.length === 0 ? (
          <span className="text-xs text-slate-400">none configured</span>
        ) : null}
      </div>
      {hint ? <p className="mt-1 text-xs text-slate-400">{hint}</p> : null}
      {errors.map((message) => (
        <p key={message} role="alert" className="mt-1 text-xs text-red-700">
          {message}
        </p>
      ))}
    </fieldset>
  );
}
