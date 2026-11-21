import { useState } from "react";

import type { FixProposal } from "../../api/types";
import { formatDateTime, formatRelativeTime } from "../alerts/alertFormat";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Skeleton } from "../ui/Skeleton";
import { StatusChip } from "../ui/StatusChip";
import { TextInput } from "../ui/TextInput";
import { FIX_KIND_LABELS, PROPOSAL_STATUS_META } from "./fixLabels";
import { RuleDiff } from "./RuleDiff";
import { RunbookStepPreview } from "./RunbookStepPreview";
import { useCurrentRuleLines } from "./useCurrentRuleLines";
import type { FixDecisionKind } from "./useFixDecision";
import { useRunbookSteps } from "./useRunbookSteps";
import { toYamlLines } from "./yamlLite";

interface FixProposalCardProps {
  readonly proposal: FixProposal;
  readonly alertTitle: string;
  readonly busyKind: FixDecisionKind | null;
  readonly error: string | null;
  readonly onOpenAlert: (alertId: string) => void;
  readonly onDecide: (decision: FixDecisionKind, comment: string) => void;
}

function RuleChange({ proposal, rule }: { readonly proposal: FixProposal; readonly rule: object }) {
  const current = useCurrentRuleLines(proposal.rule_id);
  if (current.error) return <p className="text-meta text-critical-ink">{current.error}</p>;
  if (!current.lines) return <Skeleton className="h-24 w-full" />;
  return <RuleDiff before={current.lines} after={toYamlLines(rule)} />;
}

function RunbookChange({ proposal }: { readonly proposal: FixProposal }) {
  const runbook = useRunbookSteps(proposal.runbook_id);
  const step = proposal.proposed_runbook_step;
  if (!step) return null;
  if (runbook.error) return <p className="text-meta text-critical-ink">{runbook.error}</p>;
  if (runbook.steps === null) return <Skeleton className="h-24 w-full" />;
  return <RunbookStepPreview steps={runbook.steps} step={step} />;
}

/** One fix proposal card: summary, alert context, clean line diff or step preview, and actions. */
export function FixProposalCard({
  proposal,
  alertTitle,
  busyKind,
  error,
  onOpenAlert,
  onDecide,
}: FixProposalCardProps) {
  const [comment, setComment] = useState("");
  const isPending = proposal.status === "pending";
  const isBusy = busyKind !== null;
  const statusMeta = PROPOSAL_STATUS_META[proposal.status];
  const proposer = proposal.proposed_by.display_name ?? proposal.proposed_by.id;

  return (
    <Card as="li" className="list-none space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip tone="info">{FIX_KIND_LABELS[proposal.kind]}</StatusChip>
            <StatusChip tone={statusMeta.tone}>{statusMeta.label}</StatusChip>
          </div>
          <h3 className="pt-1 text-row font-semibold break-words whitespace-pre-wrap text-ink">
            {proposal.description}
          </h3>
          <p className="text-meta text-ink-2">
            Proposed by {proposer} ·{" "}
            <time dateTime={proposal.created_at} title={formatDateTime(proposal.created_at)}>
              {formatRelativeTime(proposal.created_at)}
            </time>
            {proposal.rule_id ? ` · Rule ${proposal.rule_id}` : ""}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-tile bg-panel px-3.5 py-2.5 text-meta">
        <span className="font-medium text-ink-2">Alert</span>
        <button
          type="button"
          onClick={() => {
            onOpenAlert(proposal.alert_id);
          }}
          className="min-w-0 text-left font-medium break-words text-accent-ink hover:underline"
        >
          {alertTitle}
        </button>
      </div>

      {proposal.proposed_rule ? (
        <RuleChange proposal={proposal} rule={proposal.proposed_rule} />
      ) : null}

      {proposal.proposed_runbook_step ? <RunbookChange proposal={proposal} /> : null}

      {isPending ? (
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <div className="min-w-[12rem] flex-1">
            <label className="sr-only" htmlFor={`proposal-note-${proposal.id}`}>
              Optional note
            </label>
            <TextInput
              id={`proposal-note-${proposal.id}`}
              type="text"
              value={comment}
              placeholder="Add a note (optional)"
              disabled={isBusy}
              onChange={(event) => {
                setComment(event.target.value);
              }}
              className="h-9 text-meta"
            />
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              disabled={isBusy}
              isLoading={busyKind === "reject"}
              onClick={() => {
                onDecide("reject", comment);
              }}
            >
              Reject
            </Button>
            <Button
              variant="primary"
              disabled={isBusy}
              isLoading={busyKind === "accept"}
              onClick={() => {
                onDecide("accept", comment);
              }}
            >
              Accept
            </Button>
          </div>
        </div>
      ) : (
        <p className="text-meta text-ink-2">
          {statusMeta.label} by{" "}
          {proposal.decided_by?.display_name ?? proposal.decided_by?.id ?? "Unknown"}
          {proposal.decided_at ? ` · ${formatRelativeTime(proposal.decided_at)}` : ""}
          {proposal.decision_comment ? ` · “${proposal.decision_comment}”` : ""}
        </p>
      )}

      {error ? (
        <p
          role="alert"
          className="rounded-tile border border-critical/30 bg-critical/8 px-3.5 py-2.5 text-meta text-critical-ink"
        >
          {error}
        </p>
      ) : null}
    </Card>
  );
}
