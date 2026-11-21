import { Card } from "../ui/Card";
import { ModelMark } from "../ui/ModelMark";
import { StatusChip } from "../ui/StatusChip";
import { Skeleton } from "../ui/Skeleton";
import { useLlmStatus, type LlmStatus } from "./useLlmStatus";

function connection(status: LlmStatus): { tone: "success" | "warning" | "neutral"; text: string } {
  if (!status.is_enabled) return { tone: "neutral", text: "Off" };
  if (status.is_reachable === false) return { tone: "warning", text: "Not reachable" };
  if (status.latency_ms === null) return { tone: "neutral", text: "Checking" };
  return { tone: "success", text: `Connected · ${String(status.latency_ms)} ms` };
}

/** Which model drafts runbooks, mappings and fixes, where it runs, and the privacy promise. */
export function AiAssistantCard() {
  const { status, error } = useLlmStatus();
  return (
    <Card className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-row font-semibold">AI assistant</h2>
          <p className="text-meta text-ink-2">
            Reads runbooks, suggests mappings and drafts fixes. A person always approves.
          </p>
        </div>
        {status ? (
          <StatusChip tone={connection(status).tone}>{connection(status).text}</StatusChip>
        ) : null}
      </div>
      {status === null ? (
        error ? (
          <p className="text-meta text-warning-ink">{error}</p>
        ) : (
          <Skeleton className="h-16 rounded-tile" />
        )
      ) : (
        <div className="flex items-center gap-4 rounded-tile bg-fill px-4 py-3.5">
          <span className="flex size-12 shrink-0 items-center justify-center rounded-tile bg-card text-ink shadow-tile">
            <ModelMark model={status.model} size={26} />
          </span>
          <div className="min-w-0">
            <p className="truncate text-row font-semibold">
              {status.is_enabled ? (status.model ?? "Unknown model") : "AI assistant is off"}
            </p>
            <p className="truncate text-meta text-ink-2">
              {status.provider_host ? `Runs on ${status.provider_host}` : "No provider configured"}
            </p>
          </div>
        </div>
      )}
      {status ? <p className="text-meta text-ink-2">{status.privacy_note}</p> : null}
    </Card>
  );
}
