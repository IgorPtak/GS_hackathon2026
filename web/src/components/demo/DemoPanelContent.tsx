import { cx } from "../../lib/cx";
import type { TabId } from "../../lib/tabs";
import { Icon, type IconName } from "../ui/icons";
import { Spinner } from "../ui/Spinner";
import { StatusChip } from "../ui/StatusChip";
import { useDemoActions, type DemoActionId } from "./useDemoActions";

interface DemoPanelContentProps {
  readonly onNavigate?: (tab: TabId) => void;
  readonly onAfterNavigate?: () => void;
}

interface ActionRowProps {
  readonly title: string;
  readonly description: string;
  readonly icon: IconName;
  readonly isBusy: boolean;
  readonly isDisabled: boolean;
  readonly badge?: { readonly text: string; readonly tone: "success" | "critical" };
  readonly isHighlighted?: boolean;
  readonly onClick: () => void;
}

function ActionRow({
  title,
  description,
  icon,
  isBusy,
  isDisabled,
  badge,
  isHighlighted = false,
  onClick,
}: ActionRowProps) {
  return (
    <button
      type="button"
      disabled={isDisabled}
      aria-busy={isBusy || undefined}
      onClick={onClick}
      className={cx(
        "flex w-full items-center gap-4 rounded-tile border border-hairline bg-card px-4 py-3.5 text-left transition-colors hover:bg-fill disabled:cursor-not-allowed disabled:opacity-55",
        isHighlighted && "border-critical/35 bg-critical/6 hover:bg-critical/10",
      )}
    >
      <span
        className={cx(
          "flex size-10 shrink-0 items-center justify-center rounded-full",
          isHighlighted ? "bg-critical/12 text-critical-ink" : "bg-fill text-ink",
        )}
      >
        {isBusy ? <Spinner size={18} /> : <Icon name={icon} size={20} />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-body font-semibold text-ink">{title}</span>
          {badge ? <StatusChip tone={badge.tone}>{badge.text}</StatusChip> : null}
        </span>
        <span className="mt-0.5 block text-meta text-ink-2">{description}</span>
      </span>
      <Icon name="chevron" size={16} className="shrink-0 -rotate-90 text-ink-3" />
    </button>
  );
}

/** Five one-click demo triggers shared by /demo and the Shift+D floating sheet. */
export function DemoPanelContent({ onNavigate, onAfterNavigate }: DemoPanelContentProps) {
  const actions = useDemoActions({ onNavigate, onAfterNavigate });
  const isBusy = (id: DemoActionId) => actions.busyAction === id;
  const isAnyBusy = actions.busyAction !== null;

  return (
    <div className="space-y-2.5">
      <ActionRow
        title="Send rates alert"
        description="Send a fresh EUR 25M rejected trade to the Rates team."
        icon="send"
        isBusy={isBusy("rates")}
        isDisabled={isAnyBusy}
        onClick={() => {
          void actions.sendRatesAlert();
        }}
      />
      <ActionRow
        title="Settlements workflow failure"
        description="Trigger a fresh workflow failure, runbook retries and a phone approval."
        icon="escalate"
        isBusy={isBusy("settlements")}
        isDisabled={isAnyBusy}
        onClick={() => {
          void actions.sendSettlementsFailure();
        }}
      />
      <ActionRow
        title="Send 500 duplicates"
        description="Stream 500 identical events in 5 batches so they fold into one alert."
        icon="layers"
        isBusy={isBusy("duplicates")}
        isDisabled={isAnyBusy}
        onClick={() => {
          void actions.sendDuplicates();
        }}
      />
      <ActionRow
        title={actions.isSmsDown ? "SMS gateway up" : "SMS gateway down"}
        description={
          actions.isSmsDown
            ? "Restore the mock SMS gateway so queued deliveries resume with zero loss."
            : "Simulate an SMS outage to show automatic retries without losing messages."
        }
        icon={actions.isSmsDown ? "phone" : "signalOff"}
        isBusy={isBusy("sms_outage")}
        isDisabled={isAnyBusy}
        isHighlighted={actions.isSmsDown}
        badge={
          actions.isSmsDown
            ? { text: "Outage active", tone: "critical" }
            : { text: "Online", tone: "success" }
        }
        onClick={() => {
          void actions.toggleSmsGateway();
        }}
      />
      <ActionRow
        title="Jury sample: unknown schema"
        description="Send a never-seen JSON payload and open Connect a system to map it."
        icon="connect"
        isBusy={isBusy("unknown_schema")}
        isDisabled={isAnyBusy}
        onClick={() => {
          void actions.sendUnknownSample();
        }}
      />
    </div>
  );
}
