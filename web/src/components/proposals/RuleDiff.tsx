import { diffLines, type DiffKind } from "./lineDiff";

const STYLE: Record<DiffKind, string> = {
  same: "text-slate-600",
  add: "bg-green-50 text-green-900",
  remove: "bg-red-50 text-red-900",
};
const MARK: Record<DiffKind, string> = { same: " ", add: "+", remove: "-" };

interface RuleDiffProps {
  readonly before: readonly string[];
  readonly after: readonly string[];
}

/** Line-by-line diff; unchanged runs far from a change are collapsed. */
export function RuleDiff({ before, after }: RuleDiffProps) {
  const all = diffLines(before, after);
  const changed = all.map((line) => line.kind !== "same");
  const isNear = (index: number): boolean => {
    for (let k = Math.max(0, index - 2); k <= Math.min(all.length - 1, index + 2); k += 1) {
      if (changed[k]) return true;
    }
    return false;
  };
  const hasChange = changed.some(Boolean);
  if (!hasChange) return <p className="text-sm text-slate-500">No changes to the rule.</p>;
  return (
    <pre
      aria-label="Rule diff"
      className="max-h-80 overflow-auto rounded border border-slate-200 bg-white py-1 text-xs"
    >
      {all.map((line, index) =>
        isNear(index) ? (
          <div key={index} className={`px-2 whitespace-pre-wrap break-all ${STYLE[line.kind]}`}>
            {MARK[line.kind]} {line.text}
          </div>
        ) : index === 0 || isNear(index - 1) ? (
          <div key={index} className="px-2 text-slate-400">
            ...
          </div>
        ) : null,
      )}
    </pre>
  );
}
