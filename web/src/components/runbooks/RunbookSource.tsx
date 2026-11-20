/** Original runbook text, always available next to the steps. */
export function RunbookSource({ source, format }: { source: string; format: string }) {
  return (
    <div>
      <p className="mb-2 text-meta font-medium text-ink-2">Original text ({format})</p>
      <pre className="max-h-96 overflow-auto rounded-tile bg-fill p-4 font-mono text-meta break-words whitespace-pre-wrap text-ink">
        {source}
      </pre>
    </div>
  );
}
