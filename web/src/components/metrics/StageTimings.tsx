import type { MetricsSummary } from "./useMetricsSummary";

function format(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "No traffic yet";
  if (seconds < 1) return `${String(Math.round(seconds * 1000))} ms`;
  return `${seconds.toFixed(2)} s`;
}

/** Where an alert spends its time (p99): waiting in the outbox, sending, and the whole trip. */
export function StageTimings({ summary }: { readonly summary: MetricsSummary }) {
  const stages = [
    {
      label: "Saved, waiting to be handed on",
      hint: "Outbox to relay",
      value: summary.relay_wait_p99_seconds,
    },
    {
      label: "Handed on, being sent",
      hint: "Relay to first delivery result",
      value: summary.delivery_p99_seconds,
    },
    {
      label: "The whole trip",
      hint: "Event received to delivered",
      value: summary.e2e_latency_p99_seconds,
    },
  ];
  const longest = Math.max(0.001, ...stages.map((stage) => stage.value ?? 0));
  return (
    <section aria-labelledby="stages-heading" className="space-y-3">
      <h2 id="stages-heading" className="text-row font-semibold text-ink">
        Where the time goes <span className="text-meta font-normal text-ink-2">p99</span>
      </h2>
      <ul className="space-y-3 rounded-card border border-hairline bg-card p-5 shadow-card">
        {stages.map((stage) => {
          const share = stage.value == null ? 0 : Math.max(2, (stage.value / longest) * 100);
          return (
            <li
              key={stage.label}
              className="grid gap-1.5 sm:grid-cols-[260px_1fr_88px] sm:items-center sm:gap-4"
            >
              <div>
                <p className="text-body">{stage.label}</p>
                <p className="text-caption text-ink-3">{stage.hint}</p>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-fill" aria-hidden="true">
                <div
                  className="h-full rounded-full bg-accent transition-[width] duration-700 ease-[var(--ease-soft)]"
                  style={{ width: `${String(share)}%` }}
                />
              </div>
              <p className="num text-body font-medium sm:text-right">{format(stage.value)}</p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
