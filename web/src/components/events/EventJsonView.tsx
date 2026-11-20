interface EventJsonViewProps {
  readonly payload: Record<string, unknown>;
}

export function EventJsonView({ payload }: EventJsonViewProps) {
  return (
    <details className="mt-1">
      <summary className="cursor-pointer text-xs text-slate-600">Payload</summary>
      <pre className="mt-1 max-h-64 overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-100">
        {JSON.stringify(payload, null, 2)}
      </pre>
    </details>
  );
}
