import { useState } from "react";

import { useEventStream } from "../../hooks/useEventStream";
import { FixProposalCard } from "./FixProposalCard";
import { useFixDecision } from "./useFixDecision";
import { useFixProposals } from "./useFixProposals";

/** Fix proposals owned by one team, live from fix_proposal.updated; pending by default. */
export function FixProposalReview({ team }: { team: string }) {
  const [isShowingDecided, setIsShowingDecided] = useState(false);
  const proposals = useFixProposals(team, isShowingDecided);
  const { apply, reload } = proposals;
  const decision = useFixDecision(team, apply);
  useEventStream(team, {
    "fix_proposal.updated": (event) => {
      apply(event.fix_proposal);
    },
    onReconnect: reload,
  });

  return (
    <section aria-labelledby="fix-proposals-title" className="mt-8">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 id="fix-proposals-title" className="text-xl font-semibold">
          Fix proposals
        </h2>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={isShowingDecided}
            onChange={(event) => {
              setIsShowingDecided(event.target.checked);
            }}
          />
          Show decided
        </label>
      </div>
      {proposals.isLoading ? (
        <p className="text-sm text-slate-500">Loading fix proposals...</p>
      ) : null}
      {proposals.error ? (
        <p role="alert" className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          Cannot load fix proposals ({proposals.error}).{" "}
          <button type="button" className="underline" onClick={proposals.reload}>
            Retry
          </button>
        </p>
      ) : null}
      {!proposals.isLoading && !proposals.error && proposals.items.length === 0 ? (
        <p className="text-sm text-slate-500">
          {isShowingDecided ? "No fix proposals" : "No pending fix proposals"}
        </p>
      ) : null}
      <ul className="space-y-3">
        {proposals.items.map((proposal) => (
          <FixProposalCard
            key={proposal.id}
            proposal={proposal}
            isBusy={decision.busyId === proposal.id}
            error={decision.errors[proposal.id] || null}
            onDecide={(kind, comment) => {
              void decision.decide(proposal.id, kind, comment);
            }}
          />
        ))}
      </ul>
    </section>
  );
}
