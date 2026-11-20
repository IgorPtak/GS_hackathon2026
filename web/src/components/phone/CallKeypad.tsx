const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"] as const;

interface CallKeypadProps {
  disabled: boolean;
  onKey: (key: string) => void;
}

/** 12-key phone keypad. */
export function CallKeypad({ disabled, onKey }: CallKeypadProps) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {KEYS.map((key) => (
        <button
          key={key}
          type="button"
          disabled={disabled}
          aria-label={`Key ${key}`}
          onClick={() => {
            onKey(key);
          }}
          className="rounded-full bg-slate-700 py-2 text-lg font-semibold text-white hover:bg-slate-600 disabled:opacity-40"
        >
          {key}
        </button>
      ))}
    </div>
  );
}
