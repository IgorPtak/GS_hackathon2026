import { Button } from "../ui/Button";
import { Icon } from "../ui/icons";
import { Select } from "../ui/Select";
import { TextInput } from "../ui/TextInput";
import { SEVERITIES, summarizeValueMap } from "./schemaDraft";

interface ValueMapTableProps {
  readonly valueMap: Readonly<Record<string, string>>;
  readonly onChange: (next: Record<string, string>) => void;
}

/** Raw value -> severity table for the severity mapping, summarised until opened. */
export function ValueMapTable({ valueMap, onChange }: ValueMapTableProps) {
  const rows = Object.entries(valueMap);
  const hasBlank = rows.some(([raw]) => raw === "");

  function replaceRow(index: number, raw: string, value: string) {
    onChange(Object.fromEntries(rows.map((row, i) => (i === index ? [raw, value] : row))));
  }

  return (
    <details className="group mt-2">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-meta text-ink-2 hover:text-ink">
        <Icon
          name="chevron"
          size={14}
          className="-rotate-90 transition-transform group-open:rotate-0"
        />
        {rows.length === 0 ? "No value translations" : summarizeValueMap(valueMap)}
        <span className="text-accent-ink">Edit</span>
      </summary>
      <div className="mt-3 space-y-2">
        {rows.map(([raw, value], index) => (
          <div key={index} className="grid grid-cols-[1fr_auto_1fr_auto] items-center gap-2">
            <TextInput
              aria-label="Value in your event"
              value={raw}
              className="font-mono"
              onChange={(e) => {
                replaceRow(index, e.target.value, value);
              }}
            />
            <span aria-hidden="true" className="text-ink-2">
              →
            </span>
            <Select
              aria-label={`Severity for ${raw}`}
              value={value}
              options={[...new Set([...SEVERITIES, value])].map((s) => ({ value: s, label: s }))}
              onChange={(next) => {
                replaceRow(index, raw, next);
              }}
            />
            <button
              type="button"
              aria-label={`Remove ${raw}`}
              onClick={() => {
                onChange(Object.fromEntries(rows.filter((_, i) => i !== index)));
              }}
              className="flex size-8 items-center justify-center rounded-full text-ink-2 hover:bg-fill hover:text-ink"
            >
              <Icon name="cross" size={14} />
            </button>
          </div>
        ))}
        <Button
          variant="ghost"
          icon="plus"
          disabled={hasBlank}
          onClick={() => {
            onChange({ ...valueMap, "": "warning" });
          }}
        >
          Add a value
        </Button>
      </div>
    </details>
  );
}
