import { useState, type ReactNode } from "react";

import { PRODUCT_NAME } from "../../lib/brand";
import { cx } from "../../lib/cx";
import { markWelcomeSeen, useHasSeenWelcome } from "../../lib/onboarding";
import type { TabId } from "../../lib/tabs";
import { TEST_CONSOLE_SHORTCUT } from "../../lib/testConsole";
import { useSendTestAlert } from "../alerts/useSendTestAlert";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Icon, type IconName } from "../ui/icons";

interface WelcomeDialogProps {
  readonly personId: string;
  readonly teamId: string;
  readonly teamLabel: string;
  readonly onNavigate: (tab: TabId) => void;
}

const PAGE_TITLES = [`Welcome to ${PRODUCT_NAME}`, "How an alert reaches you", "Try it now"];

function Feature({
  icon,
  title,
  children,
}: {
  icon: IconName;
  title: string;
  children: ReactNode;
}) {
  return (
    <li className="flex gap-4">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-fill text-ink">
        <Icon name={icon} size={19} />
      </span>
      <div>
        <p className="text-body font-semibold">{title}</p>
        <p className="text-meta text-ink-2">{children}</p>
      </div>
    </li>
  );
}

const FLOW: readonly { icon: IconName; title: string; hint: string }[] = [
  {
    icon: "connect",
    title: "An event arrives",
    hint: "From a webhook, Alertmanager or a log file.",
  },
  { icon: "rules", title: "A rule matches", hint: "Your team's rules decide what is a problem." },
  { icon: "inbox", title: "One alert", hint: "Repeats are counted, not sent again." },
  {
    icon: "bell",
    title: "The right person is told",
    hint: "Email, text or a call, in working hours.",
  },
];

function WelcomePage() {
  return (
    <div className="flex flex-col gap-6">
      <p className="text-body text-ink-2">
        {PRODUCT_NAME} watches your systems and tells the right person when something breaks. You
        stay in charge: it never changes anything without a person saying yes.
      </p>
      <ul className="flex flex-col gap-5">
        <Feature icon="inbox" title="Inbox">
          What needs you now. 500 identical errors show up as one alert with a count.
        </Feature>
        <Feature icon="rules" title="Rules">
          What counts as a problem, in plain words. Try a rule on past events before you save it.
        </Feature>
        <Feature icon="approval" title="Approvals">
          Runbooks and the AI only suggest fixes. Anything risky waits here for a teammate.
        </Feature>
      </ul>
    </div>
  );
}

function FlowPage() {
  return (
    <ol className="grid gap-3 min-[560px]:grid-cols-4">
      {FLOW.map((step, index) => (
        <li
          key={step.title}
          className="relative flex flex-col gap-3 rounded-tile border border-hairline bg-panel p-4"
        >
          <span className="flex items-center justify-between">
            <span className="flex size-9 items-center justify-center rounded-full bg-card text-ink shadow-tile">
              <Icon name={step.icon} size={18} />
            </span>
            <span className="num text-caption text-ink-3">{index + 1}</span>
          </span>
          <span>
            <span className="block text-body font-semibold leading-tight">{step.title}</span>
            <span className="mt-1 block text-meta text-ink-2">{step.hint}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

function TryPage({ teamLabel }: { teamLabel: string }) {
  return (
    <div className="flex flex-col gap-5">
      <p className="text-body text-ink-2">
        Send a test alert for {teamLabel} and watch it land in your Inbox within seconds.
      </p>
      <ul className="flex flex-col gap-3 rounded-tile border border-hairline bg-panel p-4">
        <li className="flex items-center gap-3 text-meta text-ink-2">
          <Icon name="home" size={17} className="shrink-0 text-ink" />
          Home has a short checklist that takes a new team from nothing to its first alert.
        </li>
        <li className="flex items-center gap-3 text-meta text-ink-2">
          <kbd className="shrink-0 rounded-md border border-hairline bg-card px-1.5 py-px font-sans text-caption font-medium text-ink">
            {TEST_CONSOLE_SHORTCUT}
          </kbd>
          Opens the test console: outages, duplicate storms and the on-call phone.
        </li>
      </ul>
    </div>
  );
}

/** A three-page welcome shown once per person after signing in on this browser; Settings reopens it. */
export function WelcomeDialog({ personId, teamId, teamLabel, onNavigate }: WelcomeDialogProps) {
  const hasSeen = useHasSeenWelcome(personId);
  const [page, setPage] = useState(0);
  const testAlert = useSendTestAlert(teamId, teamLabel);
  const isLast = page === PAGE_TITLES.length - 1;

  function finish() {
    markWelcomeSeen(personId);
    setPage(0);
  }

  return (
    <Dialog
      isOpen={!hasSeen}
      onClose={finish}
      width="lg"
      title={PAGE_TITLES[page] ?? ""}
      subtitle={`Step ${String(page + 1)} of ${String(PAGE_TITLES.length)}`}
      footer={
        <>
          <span className="mr-auto flex gap-1.5" aria-hidden>
            {PAGE_TITLES.map((title, index) => (
              <span
                key={title}
                className={cx(
                  "h-1.5 rounded-full transition-[width,background-color] duration-500 ease-soft",
                  index === page ? "w-5 bg-ink" : "w-1.5 bg-hairline",
                )}
              />
            ))}
          </span>
          {page === 0 ? (
            <Button variant="ghost" onClick={finish}>
              Skip
            </Button>
          ) : (
            <Button
              variant="ghost"
              onClick={() => {
                setPage(page - 1);
              }}
            >
              Back
            </Button>
          )}
          {isLast ? (
            <Button
              variant="primary"
              icon="send"
              isLoading={testAlert.isSending}
              onClick={() => {
                void testAlert.send().then(() => {
                  finish();
                  onNavigate("inbox");
                });
              }}
            >
              Send a test alert
            </Button>
          ) : (
            <Button
              variant="primary"
              onClick={() => {
                setPage(page + 1);
              }}
            >
              Next
            </Button>
          )}
        </>
      }
    >
      <div key={page} className="animate-fade-up pb-2">
        {page === 0 ? <WelcomePage /> : null}
        {page === 1 ? <FlowPage /> : null}
        {page === 2 ? <TryPage teamLabel={teamLabel} /> : null}
      </div>
    </Dialog>
  );
}
