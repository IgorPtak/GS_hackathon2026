import { ApprovalQueue } from "../components/approvals/ApprovalQueue";

export function ApprovalsPage({ teamId }: { teamId: string | null }) {
  if (teamId === null) {
    return (
      <section className="rounded-lg border border-dashed border-slate-300 bg-white p-6">
        <h2 className="text-xl font-semibold">Approvals</h2>
        <p className="mt-2 text-sm text-slate-600">Select a team to see its pending approvals.</p>
      </section>
    );
  }
  return <ApprovalQueue key={teamId} team={teamId} />;
}
