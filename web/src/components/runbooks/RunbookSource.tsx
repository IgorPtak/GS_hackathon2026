/** Original runbook text; collapsible on narrow screens, always open from `lg`. */
export function RunbookSource({ source, format }: { source: string; format: string }) {
  return (
    <details open className="rounded border border-slate-200 lg:[&>summary]:pointer-events-none">
      <summary className="cursor-pointer bg-slate-50 px-3 py-1.5 text-sm font-semibold text-slate-700">
        Source ({format})
      </summary>
      <pre className="max-h-96 overflow-auto p-3 font-mono text-xs break-words whitespace-pre-wrap">
        {source}
      </pre>
    </details>
  );
}
