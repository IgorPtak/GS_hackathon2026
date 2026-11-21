import { useState } from "react";

import type { TabId } from "../../lib/tabs";
import { cx } from "../../lib/cx";
import { setChecklistHidden, useIsChecklistHidden } from "../../lib/onboarding";
import { useSendTestAlert } from "../alerts/useSendTestAlert";
import { Button } from "../ui/Button";
import { Icon } from "../ui/icons";
import { Skeleton } from "../ui/Skeleton";
import { useSetupProgress, type SetupProgress, type SetupStepId } from "./useSetupProgress";

interface SetupStep {
  readonly id: SetupStepId;
  readonly title: string;
  readonly todo: string;
  readonly done: (progress: SetupProgress) => string;
  readonly action: string;
}

function plural(count: number, one: string, many: string): string {
  return `${String(count)} ${count === 1 ? one : many}`;
}

const STEPS: readonly SetupStep[] = [
  {
    id: "connect",
    title: "Connect a system",
    todo: "Paste one sample event. Beacon suggests how to read its fields.",
    done: (p) => `Beacon understands ${plural(p.profileCount, "kind", "kinds")} of events.`,
    action: "Connect",
  },
  {
    id: "rule",
    title: "Write a rule",
    todo: "Say what counts as a problem, and try it on past events before you save.",
    done: (p) => `${plural(p.ruleCount, "rule is", "rules are")} watching for your team.`,
    action: "New rule",
  },
  {
    id: "people",
    title: "Choose who is told",
    todo: "Email, a text or a call, and only within working hours.",
    done: (p) => `${plural(p.notifiedCount, "person", "people")} will be told.`,
    action: "Open",
  },
  {
    id: "alert",
    title: "Send a test alert",
    todo: "It lands in your Inbox within seconds.",
    done: () => "Alerts reach your Inbox.",
    action: "Send",
  },
];

const TAB_FOR_STEP: Record<SetupStepId, TabId> = {
  connect: "connect",
  rule: "rules",
  people: "people",
  alert: "inbox",
};

interface GettingStartedCardProps {
  readonly teamId: string;
  readonly teamLabel: string;
  readonly onNavigate: (tab: TabId) => void;
}

/**
 * Home checklist for a team that is new to Beacon: four steps from "nothing" to "alerts reach
 * us". Each step ticks itself from live data, so it cannot claim a step that does not work yet.
 */
export function GettingStartedCard({ teamId, teamLabel, onNavigate }: GettingStartedCardProps) {
  const isHidden = useIsChecklistHidden(teamId);
  const progress = useSetupProgress(teamId, !isHidden);
  const testAlert = useSendTestAlert(teamId, teamLabel);
  const [isExpanded, setIsExpanded] = useState(false);
  if (isHidden) return null;

  const done = progress.done;
  const doneCount = done?.size ?? 0;
  const nextStep = done ? STEPS.find((step) => !done.has(step.id)) : undefined;
  const isComplete = done !== null && nextStep === undefined;
  // A team that is fully set up gets one quiet line; the steps stay one click away.
  const isCompact = isComplete && !isExpanded;

  function runStep(step: SetupStep) {
    if (step.id === "alert" && !done?.has("alert")) {
      void testAlert.send().then(() => {
        onNavigate("inbox");
      });
      return;
    }
    onNavigate(TAB_FOR_STEP[step.id]);
  }

  return (
    <section
      aria-labelledby="setup-title"
      className={cx(
        "animate-fade-up rounded-card border border-hairline bg-card shadow-card",
        isCompact ? "px-6 py-4" : "p-6",
      )}
    >
      <div className={cx("flex justify-between gap-4", isCompact ? "items-center" : "items-start")}>
        {isCompact ? (
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-success/15 text-success-ink">
            <Icon name="check" size={19} />
          </span>
        ) : null}
        <div className="min-w-0 flex-1">
          <h2
            id="setup-title"
            className={cx(
              "font-semibold tracking-tight",
              isCompact ? "text-row" : "text-card-title",
            )}
          >
            {isComplete ? `${teamLabel} is set up` : `Set up ${teamLabel}`}
          </h2>
          <p className="mt-0.5 text-meta text-ink-2">
            {isComplete
              ? "Events come in, rules catch problems and the right people are told."
              : "About five minutes. Each step ticks itself once it really works."}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {isComplete ? (
            <Button
              variant="ghost"
              aria-expanded={isExpanded}
              onClick={() => {
                setIsExpanded(!isExpanded);
              }}
            >
              {isExpanded ? "Fewer details" : "Show steps"}
            </Button>
          ) : (
            <span className="num text-meta text-ink-2" aria-live="polite">
              {done === null ? "" : `${String(doneCount)} of ${String(STEPS.length)}`}
            </span>
          )}
          <Button
            variant="ghost"
            onClick={() => {
              setChecklistHidden(teamId, true);
            }}
          >
            Hide
          </Button>
        </div>
      </div>
      {isCompact ? null : (
        <div
          className="mt-4 h-1 overflow-hidden rounded-full bg-fill"
          role="progressbar"
          aria-label="Setup progress"
          aria-valuemin={0}
          aria-valuemax={STEPS.length}
          aria-valuenow={doneCount}
        >
          <div
            className="h-full rounded-full bg-success transition-[width] duration-700 ease-soft"
            style={{ width: `${String((doneCount / STEPS.length) * 100)}%` }}
          />
        </div>
      )}
      {isCompact ? null : done === null ? (
        <div className="mt-5 flex flex-col gap-3">
          {STEPS.map((step) => (
            <Skeleton key={step.id} className="h-12 w-full" />
          ))}
        </div>
      ) : (
        <ol className="mt-3 flex flex-col">
          {STEPS.map((step, index) => {
            const isDone = done.has(step.id);
            const isNext = step === nextStep;
            return (
              <li
                key={step.id}
                className={cx(
                  "flex items-center gap-4 rounded-tile px-3 py-3 transition-colors -mx-3",
                  isNext && "bg-fill/60",
                )}
              >
                <span
                  className={cx(
                    "flex size-8 shrink-0 items-center justify-center rounded-full text-meta font-semibold transition-colors duration-500",
                    isDone ? "bg-success/15 text-success-ink" : "bg-fill text-ink-2",
                    isNext && "bg-ink text-window",
                  )}
                  aria-hidden
                >
                  {isDone ? <Icon name="check" size={16} /> : index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className={cx("text-body font-semibold", isDone && "text-ink-2")}>
                    {step.title}
                    <span className="sr-only">{isDone ? " (done)" : " (to do)"}</span>
                  </p>
                  <p className="text-meta text-ink-2">{isDone ? step.done(progress) : step.todo}</p>
                </div>
                <Button
                  variant={isNext ? "primary" : "ghost"}
                  isLoading={step.id === "alert" && testAlert.isSending}
                  onClick={() => {
                    runStep(step);
                  }}
                  aria-label={isDone ? `Open: ${step.title}` : `${step.action}: ${step.title}`}
                >
                  {isDone ? "Open" : step.action}
                </Button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
