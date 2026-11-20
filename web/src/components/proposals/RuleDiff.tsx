import { cx } from "../../lib/cx";
import { diffLines, type DiffKind } from "./lineDiff";

const LINE_STYLE: Record<DiffKind, string> = {
  same: "text-ink-2",
  add: "bg-success/12 text-success-ink",
  remove: "bg-critical/12 text-critical-ink",
};

const MARK: Record<DiffKind, string> = { same: " ", add: "+", remove: "−" };

interface RuleDiffProps {
  readonly before: readonly string[];
  readonly after: readonly string[];
}

/** Line-by-line rule diff: green and red tinted rows in tabular monospace. */
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

  if (!hasChange) {
    return <p className="text-meta text-ink-2">No changes to the rule.</p>;
  }

  return (
    <pre
      aria-label="Rule diff"
      className="num max-h-80 overflow-auto rounded-tile border border-hairline bg-panel py-2 font-mono text-caption leading-5"
    >
      {all.map((line, index) =>
        isNear(index) ? (
          <div
            key={index}
            className={cx(
              "flex gap-3 px-3.5 py-0.5 whitespace-pre-wrap break-all",
              LINE_STYLE[line.kind],
            )}
          >
            <span aria-hidden="true" className="w-3 shrink-0 select-none opacity-80">
              {MARK[line.kind]}
            </span>
            <span className="min-w-0 flex-1">{line.text}</span>
          </div>
        ) : index === 0 || isNear(index - 1) ? (
          <div key={index} className="px-3.5 py-0.5 text-ink-3 select-none">
            …
          </div>
        ) : null,
      )}
    </pre>
  );
}
