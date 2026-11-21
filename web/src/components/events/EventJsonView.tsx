interface EventJsonViewProps {
  readonly payload: Record<string, unknown>;
}

/** Collapsed raw payload of one event. */
export function EventJsonView({ payload }: EventJsonViewProps) {
  return (
    <details className="mt-1">
      <summary className="text-meta text-ink-2">Payload</summary>
      <pre className="mt-1 max-h-64 overflow-auto rounded-input bg-fill p-3 font-mono text-caption text-ink">
        {JSON.stringify(payload, null, 2)}
      </pre>
    </details>
  );
}
