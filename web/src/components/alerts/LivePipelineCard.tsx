import { Avatar } from "../ui/Avatar";
import { Card } from "../ui/Card";
import { PulseBars } from "../ui/PulseBars";
import { StatusChip } from "../ui/StatusChip";
import { describeNumbers, describePipeline } from "./pipelineWords";
import { usePipelineMetrics } from "./usePipelineMetrics";

/** Same-app navigation without a router: the shell listens to popstate. */
function openInsights() {
  window.history.pushState(null, "", "/insights" + window.location.search);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

/** The one bold spot of the Inbox: is everything flowing, how fast, and nothing lost. */
export function LivePipelineCard({ teamId, teamLabel }: { teamId: string; teamLabel: string }) {
  const metrics = usePipelineMetrics();
  const words = describePipeline(metrics);
  return (
    <Card className="flex flex-wrap items-center gap-x-8 gap-y-4 @container">
      <div className="flex min-w-0 items-center gap-4">
        <Avatar name={teamLabel} team={teamId} size="xl" />
        <div className="min-w-0">
          <h2 className="text-row font-semibold">{words.headline}</h2>
          <p className="text-meta text-ink-2" aria-live="polite">
            {words.detail}
          </p>
        </div>
      </div>
      <div
        className="min-w-40 flex-1"
        title={`Activity in the last minute: ${describeNumbers(metrics.rate, metrics.p99Milliseconds)}`}
      >
        <PulseBars samples={metrics.samples} />
      </div>
      <div className="flex items-center gap-3">
        <StatusChip tone={words.tone} icon={words.tone === "success" ? "check" : undefined}>
          {words.chip}
        </StatusChip>
        <button
          type="button"
          onClick={openInsights}
          className="inline-flex h-9 items-center rounded-full px-3 text-meta font-medium text-ink-2 transition-colors hover:bg-fill hover:text-ink"
        >
          Details
        </button>
      </div>
    </Card>
  );
}
