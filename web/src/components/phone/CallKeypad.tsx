interface KeypadItem {
  readonly digit: string;
  readonly letters: string;
  readonly label: string;
}

const KEYS: readonly KeypadItem[] = [
  { digit: "1", letters: "", label: "Key 1" },
  { digit: "2", letters: "ABC", label: "Key 2" },
  { digit: "3", letters: "DEF", label: "Key 3" },
  { digit: "4", letters: "GHI", label: "Key 4" },
  { digit: "5", letters: "JKL", label: "Key 5" },
  { digit: "6", letters: "MNO", label: "Key 6" },
  { digit: "7", letters: "PQRS", label: "Key 7" },
  { digit: "8", letters: "TUV", label: "Key 8" },
  { digit: "9", letters: "WXYZ", label: "Key 9" },
  { digit: "*", letters: "Reject", label: "Star, reject" },
  { digit: "0", letters: "+", label: "Key 0" },
  { digit: "#", letters: "Repeat", label: "Hash, repeat message" },
];

interface CallKeypadProps {
  readonly disabled: boolean;
  readonly onKey: (key: string) => void;
}

/** iOS-styled 12-key round grey keypad with digits and sub-labels. */
export function CallKeypad({ disabled, onKey }: CallKeypadProps) {
  return (
    <div className="mx-auto grid w-full max-w-[236px] grid-cols-3 justify-items-center gap-x-4 gap-y-2.5">
      {KEYS.map((item) => (
        <button
          key={item.digit}
          type="button"
          disabled={disabled}
          aria-label={item.label}
          onClick={() => {
            onKey(item.digit);
          }}
          className="flex size-[60px] flex-col items-center justify-center rounded-full bg-white/16 text-white backdrop-blur-md transition-colors hover:bg-white/26 active:bg-white/36 disabled:opacity-40"
        >
          <span className="text-[24px] leading-none font-normal">{item.digit}</span>
          <span className="mt-0.5 min-h-[11px] text-[9px] leading-none font-medium tracking-[0.08em] text-white/70">
            {item.letters}
          </span>
        </button>
      ))}
    </div>
  );
}
