import { HomeTile } from "../components/home/HomeTile";
import { useHomeSummary } from "../components/home/useHomeSummary";
import { LivePipelineCard } from "../components/alerts/LivePipelineCard";
import { splitAlertTitle } from "../components/alerts/alertText";
import { SeverityDot } from "../components/ui/SeverityDot";
import { PageFrame } from "../components/ui/PageFrame";
import type { ScreenProps } from "./types";

function greeting(now = new Date()): string {
  const hour = now.getHours();
  if (hour < 5 || hour >= 22) return "Good night";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function countLabel(value: number | null): string {
  return value === null ? "" : String(value);
}

/** Home: the team at a glance, each card opening its section (Revolut-style overview). */
export function HomeScreen({ teamId, teamLabel, person, onNavigate }: ScreenProps) {
  const summary = useHomeSummary(teamId);
  const firstName = person?.display_name.split(" ")[0];
  const firstApproval = summary.approvals[0];
  return (
    <PageFrame title={firstName ? `${greeting()}, ${firstName}` : greeting()} context={teamLabel}>
      <div className="flex flex-col gap-6">
        <LivePipelineCard
          onOpenDetails={() => {
            onNavigate("insights");
          }}
        />
        <div className="grid grid-cols-1 gap-6 min-[900px]:grid-cols-2">
          <HomeTile
            icon="inbox"
            title="Inbox"
            value={countLabel(summary.openAlertTotal)}
            caption={summary.openAlertTotal === 1 ? "open alert" : "open alerts"}
            onOpen={() => {
              onNavigate("inbox");
            }}
          >
            {summary.openAlerts.length > 0 ? (
              <ul className="flex flex-col gap-2">
                {summary.openAlerts.map((alert) => (
                  <li key={alert.id} className="flex items-center gap-2.5 text-body">
                    <SeverityDot severity={alert.severity} />
                    <span className="truncate">{splitAlertTitle(alert.title).title}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-body text-ink-2">All quiet. Nothing needs you right now.</p>
            )}
          </HomeTile>
          <HomeTile
            icon="approval"
            title="Approvals"
            value={String(summary.approvals.length)}
            caption="waiting for you"
            onOpen={() => {
              onNavigate("approvals");
            }}
          >
            <p className="line-clamp-2 text-body text-ink-2">
              {firstApproval
                ? firstApproval.summary
                : "Nothing to approve. Runbooks ask here first."}
            </p>
          </HomeTile>
        </div>
        <div className="grid grid-cols-1 gap-6 min-[900px]:grid-cols-3">
          <HomeTile
            icon="rules"
            title="Rules"
            value={countLabel(summary.ruleCount)}
            caption="watching your systems"
            onOpen={() => {
              onNavigate("rules");
            }}
          />
          <HomeTile
            icon="runbook"
            title="Runbooks"
            value={countLabel(summary.runbookCount)}
            caption="ready to help"
            onOpen={() => {
              onNavigate("runbooks");
            }}
          />
          <HomeTile
            icon="phone"
            title="Phone"
            caption="See what reaches the on-call phone"
            onOpen={() => {
              onNavigate("phone");
            }}
          >
            <p className="text-body text-ink-2">Calls, texts and approval codes.</p>
          </HomeTile>
        </div>
      </div>
    </PageFrame>
  );
}
