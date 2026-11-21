import { useEffect, useState } from "react";

import type { TabId } from "../../lib/tabs";
import { cx } from "../../lib/cx";
import { TEST_CONSOLE_SHORTCUT, onOpenTestConsole } from "../../lib/testConsole";
import { useSendTestAlert } from "../alerts/useSendTestAlert";
import { useDemoActions, type DemoActionId } from "../demo/useDemoActions";
import { PhoneSimulator } from "../phone/PhoneSimulator";
import { Dialog } from "../ui/Dialog";
import { Icon, type IconName } from "../ui/icons";
import { Spinner } from "../ui/Spinner";
import { LiveEventStream } from "./LiveEventStream";

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) ||
    target.isContentEditable ||
    target.closest(".cm-editor") !== null
  );
}

interface ScenarioProps {
  readonly title: string;
  readonly hint: string;
  readonly icon: IconName;
  readonly isBusy: boolean;
  readonly isDisabled: boolean;
  readonly tone?: "default" | "critical";
  readonly onRun: () => void;
}

function Scenario({
  title,
  hint,
  icon,
  isBusy,
  isDisabled,
  tone = "default",
  onRun,
}: ScenarioProps) {
  return (
    <button
      type="button"
      disabled={isDisabled}
      aria-busy={isBusy || undefined}
      onClick={onRun}
      className={cx(
        "group flex items-start gap-3 rounded-tile border p-3.5 text-left transition-[background-color,border-color,scale] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50",
        tone === "critical"
          ? "border-critical/30 bg-critical/8 hover:bg-critical/12"
          : "border-hairline bg-card hover:bg-fill/70",
      )}
    >
      <span
        className={cx(
          "flex size-9 shrink-0 items-center justify-center rounded-full transition-colors",
          tone === "critical"
            ? "bg-critical/15 text-critical-ink"
            : "bg-fill text-ink group-hover:bg-card",
        )}
      >
        {isBusy ? <Spinner size={16} /> : <Icon name={icon} size={18} />}
      </span>
      <span className="min-w-0">
        <span className="block text-body font-semibold">{title}</span>
        <span className="block text-meta text-ink-2">{hint}</span>
      </span>
    </button>
  );
}

interface TestConsoleProps {
  readonly teamId: string;
  readonly teamLabel: string;
  readonly onNavigate: (tab: TabId) => void;
}

/**
 * Everything for trying Beacon out, kept off the product screens: scenarios that send real
 * events, the raw event stream, and the on-call phone. Opens with Shift+D or `?demo=open`.
 */
export function TestConsole({ teamId, teamLabel, onNavigate }: TestConsoleProps) {
  const [isOpen, setIsOpen] = useState(
    () => new URLSearchParams(window.location.search).get("demo") === "open",
  );
  const close = () => {
    setIsOpen(false);
  };
  const actions = useDemoActions({ onNavigate, onAfterNavigate: close });
  const testAlert = useSendTestAlert(teamId, teamLabel);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const isShortcut =
        event.code === "KeyD" &&
        event.shiftKey &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey;
      if (!isShortcut || isTyping(event.target)) return;
      event.preventDefault();
      setIsOpen((value) => !value);
    };
    window.addEventListener("keydown", onKeyDown);
    const stopListening = onOpenTestConsole(() => {
      setIsOpen(true);
    });
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      stopListening();
    };
  }, []);

  const busy = actions.busyAction;
  const isAnyBusy = busy !== null || testAlert.isSending;
  const is = (id: DemoActionId) => busy === id;

  return (
    <Dialog
      isOpen={isOpen}
      onClose={close}
      variant="sheet"
      title="Test console"
      subtitle={
        <>
          Send sample events and watch them flow through. Press{" "}
          <kbd className="rounded-md border border-hairline bg-fill px-1.5 py-px font-sans text-caption font-medium text-ink">
            {TEST_CONSOLE_SHORTCUT}
          </kbd>{" "}
          to open or close.
        </>
      }
    >
      <div className="grid gap-6 pb-3 min-[900px]:grid-cols-[minmax(0,1fr)_312px]">
        <div className="flex min-w-0 flex-col gap-6">
          <section>
            <h3 className="mb-3 text-caption font-semibold tracking-wide text-ink-2 uppercase">
              Scenarios
            </h3>
            <div className="grid gap-2.5 sm:grid-cols-2">
              <Scenario
                title={`Test alert for ${teamLabel}`}
                hint="One simple alert in your team's inbox."
                icon="send"
                isBusy={testAlert.isSending}
                isDisabled={isAnyBusy}
                onRun={() => void testAlert.send()}
              />
              <Scenario
                title="Rejected EUR 25M trade"
                hint="Rates alert with a runbook and an email."
                icon="inbox"
                isBusy={is("rates")}
                isDisabled={isAnyBusy}
                onRun={() => void actions.sendRatesAlert()}
              />
              <Scenario
                title="Settlement workflow fails"
                hint="Runbook retries, then calls the phone for approval."
                icon="phone"
                isBusy={is("settlements")}
                isDisabled={isAnyBusy}
                onRun={() => void actions.sendSettlementsFailure()}
              />
              <Scenario
                title="500 identical events"
                hint="They fold into one alert with a count."
                icon="layers"
                isBusy={is("duplicates")}
                isDisabled={isAnyBusy}
                onRun={() => void actions.sendDuplicates()}
              />
              <Scenario
                title={actions.isSmsDown ? "Bring SMS back" : "Take SMS down"}
                hint={
                  actions.isSmsDown
                    ? "Outage active. Queued messages flush when it returns."
                    : "Messages wait and retry; nothing is lost."
                }
                icon={actions.isSmsDown ? "phone" : "signalOff"}
                tone={actions.isSmsDown ? "critical" : "default"}
                isBusy={is("sms_outage")}
                isDisabled={isAnyBusy}
                onRun={() => void actions.toggleSmsGateway()}
              />
              <Scenario
                title="Event from a new system"
                hint="Unknown format; opens Connect a system."
                icon="connect"
                isBusy={is("unknown_schema")}
                isDisabled={isAnyBusy}
                onRun={() => void actions.sendUnknownSample()}
              />
            </div>
          </section>
          <section className="flex min-h-0 flex-col">
            <h3 className="mb-3 flex items-center gap-2 text-caption font-semibold tracking-wide text-ink-2 uppercase">
              <span className="relative flex size-2">
                <span className="absolute inset-0 animate-ping rounded-full bg-success/60" />
                <span className="relative size-2 rounded-full bg-success" />
              </span>
              Incoming events
            </h3>
            <div className="h-[max(240px,calc(100dvh-520px))] overflow-y-auto overscroll-contain rounded-tile border border-hairline bg-panel">
              <LiveEventStream isActive={isOpen} />
            </div>
          </section>
        </div>
        <section className="flex flex-col items-center gap-3">
          <h3 className="self-start text-caption font-semibold tracking-wide text-ink-2 uppercase">
            On-call phone
          </h3>
          {isOpen ? <PhoneSimulator teamId={teamId} isDeviceOnly /> : null}
        </section>
      </div>
    </Dialog>
  );
}
