import type { SchemaProfileTestResult } from "../../api/types";

interface SchemaTestPanelProps {
  readonly result: SchemaProfileTestResult | null;
  readonly isStale: boolean;
  readonly isRunning: boolean;
  readonly error: string | null;
  readonly onRun: () => void;
}

/** Live test of the draft profile on recent events and the sample. */
export function SchemaTestPanel({
  result,
  isStale,
  isRunning,
  error,
  onRun,
}: SchemaTestPanelProps) {
  return (
    <section aria-label="Test" className="space-y-2 rounded border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold">Test on the last hour</h4>
        <button
          type="button"
          disabled={isRunning}
          onClick={onRun}
          className="rounded bg-slate-800 px-3 py-1 text-sm text-white disabled:opacity-40"
        >
          {isRunning ? "Testing..." : "Run test"}
        </button>
        {result && isStale ? (
          <span className="text-xs text-amber-700">Stale: the profile changed since this test</span>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      ) : null}
      {!result && !error ? (
        <p className="text-sm text-slate-500">Run the test to see what this profile matches.</p>
      ) : null}
      {result ? (
        <div className={isStale ? "opacity-60" : ""}>
          <p className="text-sm">
            Matched {result.events_matched} of {result.events_scanned} scanned events
          </p>
          {result.samples.length === 0 ? (
            <p className="text-sm text-slate-500">No normalized samples.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="mt-1 w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500">
                    <th className="pr-2">Event</th>
                    <th className="pr-2">Type</th>
                    <th className="pr-2">Source</th>
                    <th className="pr-2">Severity</th>
                    <th className="pr-2">Occurred at</th>
                    <th>Entity</th>
                  </tr>
                </thead>
                <tbody>
                  {result.samples.slice(0, 20).map((s, i) => (
                    <tr
                      key={`${s.event_id ?? "sample"}-${String(i)}`}
                      className="border-b border-slate-100"
                    >
                      <td className="pr-2 font-mono">{s.event_id ?? "sample"}</td>
                      <td className="pr-2">{s.normalized.type ?? "-"}</td>
                      <td className="pr-2">{s.normalized.source ?? "-"}</td>
                      <td className="pr-2">{s.normalized.severity}</td>
                      <td className="pr-2">{s.normalized.occurred_at ?? "-"}</td>
                      <td>{s.normalized.entity ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
