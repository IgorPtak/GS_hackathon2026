import { useState } from "react";

import type { FixProposal } from "../../api/types";
import { formatDateTime } from "../alerts/alertFormat";
import { RuleDiff } from "./RuleDiff";
import { RunbookStepPreview } from "./RunbookStepPreview";
import { useCurrentRuleLines } from "./useCurrentRuleLines";
import { useRunbookSteps } from "./useRunbookSteps";
import { toYamlLines } from "./yamlLite";

interface FixProposalCardProps {
  readonly proposal: FixProposal;
  readonly isBusy: boolean;
  readonly error: string | null;
  readonly onDecide: (decision: "accept" | "reject", comment: string) => void;
}

function RuleChange({ proposal, rule }: { proposal: FixProposal; rule: object }) {
  const current = useCurrentRuleLines(proposal.rule_id);
  if (current.error) return <p className="text-sm text-red-700">{current.error}</p>;
  if (!current.lines) return <p className="text-sm text-slate-500">Loading current rule...</p>;
  return <RuleDiff before={current.lines} after={toYamlLines(rule)} />;
}

function RunbookChange({ proposal }: { proposal: FixProposal }) {
  const runbook = useRunbookSteps(proposal.runbook_id);
  const step = proposal.proposed_runbook_step;
  if (!step) return null;
  if (runbook.error) return <p className="text-sm text-red-700">{runbook.error}</p>;
  if (runbook.steps === null)
    return <p className="text-sm text-slate-500">Loading current runbook...</p>;
  return <RunbookStepPreview steps={runbook.steps} step={step} />;
}

const STATUS_STYLE: Record<FixProposal["status"], string> = {
  pending: "bg-amber-100 text-amber-900",
  accepted: "bg-green-100 text-green-900",
  rejected: "bg-slate-200 text-slate-700",
};

/** One fix proposal: metadata, the change (rule diff or runbook step) and Accept / Reject. */
export function FixProposalCard({ proposal, isBusy, error, onDecide }: FixProposalCardProps) {
  const [comment, setComment] = useState("");
  const isPending = proposal.status === "pending";
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-sky-100 px-2 py-0.5 font-mono text-xs text-sky-900">
          {proposal.kind}
        </span>
        <span className={`rounded px-2 py-0.5 text-xs ${STATUS_STYLE[proposal.status]}`}>
          {proposal.status}
        </span>
      </div>
      <p className="mt-2 font-medium break-words whitespace-pre-wrap">{proposal.description}</p>
      <p className="mt-1 text-xs text-slate-500">
        Proposed by {proposal.proposed_by.display_name ?? proposal.proposed_by.id} ·{" "}
        {formatDateTime(proposal.created_at)} · alert{" "}
        <span className="font-mono">{proposal.alert_id}</span> · rule{" "}
        <span className="font-mono">{proposal.rule_id}</span>
      </p>
      {proposal.proposed_rule ? (
        <div className="mt-3">
          <RuleChange proposal={proposal} rule={proposal.proposed_rule} />
        </div>
      ) : null}
      {proposal.proposed_runbook_step ? (
        <div className="mt-3">
          <RunbookChange proposal={proposal} />
        </div>
      ) : null}
      {isPending ? (
        <>
          <label className="mt-3 block text-sm">
            <span className="sr-only">Comment</span>
            <input
              type="text"
              value={comment}
              placeholder="Comment (optional)"
              onChange={(event) => {
                setComment(event.target.value);
              }}
              className="w-full rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              disabled={isBusy}
              onClick={() => {
                onDecide("accept", comment);
              }}
              className="rounded bg-green-700 px-3 py-1.5 text-sm text-white disabled:opacity-40"
            >
              Accept
            </button>
            <button
              type="button"
              disabled={isBusy}
              onClick={() => {
                onDecide("reject", comment);
              }}
              className="rounded border border-slate-400 px-3 py-1.5 text-sm disabled:opacity-40"
            >
              Reject
            </button>
          </div>
        </>
      ) : (
        <p className="mt-3 text-xs text-slate-500">
          Decided by {proposal.decided_by?.display_name ?? proposal.decided_by?.id ?? "unknown"}
          {proposal.decided_at ? ` · ${formatDateTime(proposal.decided_at)}` : ""}
          {proposal.decision_comment ? ` · "${proposal.decision_comment}"` : ""}
        </p>
      )}
      {error ? (
        <p role="alert" className="mt-2 rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      ) : null}
    </li>
  );
}
