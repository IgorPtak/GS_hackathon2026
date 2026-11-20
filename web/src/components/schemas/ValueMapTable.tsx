import { SEVERITIES } from "./schemaDraft";

interface ValueMapTableProps {
  readonly valueMap: Readonly<Record<string, string>>;
  readonly onChange: (next: Record<string, string>) => void;
}

/** Raw value -> severity table for the severity mapping. */
export function ValueMapTable({ valueMap, onChange }: ValueMapTableProps) {
  const rows = Object.entries(valueMap);
  const hasBlank = rows.some(([raw]) => raw === "");

  function replaceRow(index: number, raw: string, value: string) {
    onChange(Object.fromEntries(rows.map((row, i) => (i === index ? [raw, value] : row))));
  }

  return (
    <details className="mt-1 text-xs">
      <summary className="cursor-pointer text-slate-600">Value map ({rows.length})</summary>
      <table className="mt-1 w-full">
        <tbody>
          {rows.map(([raw, value], index) => (
            <tr key={index}>
              <td className="pr-1 pb-1">
                <input
                  aria-label="Raw value"
                  value={raw}
                  onChange={(e) => {
                    replaceRow(index, e.target.value, value);
                  }}
                  className="w-full rounded border border-slate-300 px-1 py-0.5 font-mono"
                />
              </td>
              <td className="pr-1 pb-1">
                <select
                  aria-label={`Severity for ${raw}`}
                  value={value}
                  onChange={(e) => {
                    replaceRow(index, raw, e.target.value);
                  }}
                  className="w-full rounded border border-slate-300 px-1 py-0.5"
                >
                  {[...new Set([...SEVERITIES, value])].map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </td>
              <td className="pb-1">
                <button
                  type="button"
                  aria-label={`Remove ${raw}`}
                  onClick={() => {
                    onChange(Object.fromEntries(rows.filter((_, i) => i !== index)));
                  }}
                  className="px-1 text-slate-500"
                >
                  x
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        type="button"
        disabled={hasBlank}
        onClick={() => {
          onChange({ ...valueMap, "": "warning" });
        }}
        className="rounded border border-slate-300 bg-white px-2 py-0.5 disabled:opacity-40"
      >
        Add value
      </button>
    </details>
  );
}
