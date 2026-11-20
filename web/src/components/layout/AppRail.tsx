import type { Team } from "../../api/types";
import { PRODUCT_NAME } from "../../lib/brand";
import { GROUP_STARTS, TABS, type TabDefinition, type TabId } from "../../lib/tabs";
import type { ThemePreference } from "../../lib/theme";
import { TeamSwitcher } from "../team/TeamSwitcher";
import { BeaconLogo } from "../ui/BeaconLogo";
import type { IconName } from "../ui/icons";
import { Rail, RailDivider } from "../ui/Rail";
import { RailItem } from "../ui/RailItem";
import { ApprovalsRailItem } from "./ApprovalsRailItem";
import { ThemeToggle } from "./ThemeToggle";

const TAB_ICONS: Record<TabId, IconName> = {
  inbox: "inbox",
  approvals: "approval",
  phone: "phone",
  rules: "rules",
  connect: "connect",
  runbooks: "runbook",
  people: "people",
  insights: "insights",
};

interface AppRailProps {
  readonly activeTabId: TabId;
  readonly teams: readonly Team[];
  readonly teamId: string;
  readonly theme: ThemePreference;
  readonly onNavigate: (tab: TabDefinition) => void;
  readonly onCycleTheme: () => void;
  readonly onSelectTeam: (teamId: string) => void;
}

/** The shell rail: logo tile, page links, then appearance toggle and team switcher. */
export function AppRail({
  activeTabId,
  teams,
  teamId,
  theme,
  onNavigate,
  onCycleTheme,
  onSelectTeam,
}: AppRailProps) {
  return (
    <Rail
      logo={
        <span
          title={PRODUCT_NAME}
          className="flex size-11 items-center justify-center rounded-tile bg-ink text-window"
        >
          <BeaconLogo size={24} />
        </span>
      }
      footer={
        <>
          <ThemeToggle theme={theme} onCycle={onCycleTheme} />
          <TeamSwitcher teams={teams} selectedTeamId={teamId} onSelect={onSelectTeam} />
        </>
      }
    >
      {TABS.map((tab) => {
        const select = () => {
          onNavigate(tab);
        };
        return (
          <div key={tab.id} className="flex flex-col items-center gap-1">
            {GROUP_STARTS.includes(tab.id) ? <RailDivider /> : null}
            {tab.id === "approvals" ? (
              <ApprovalsRailItem
                team={teamId}
                href={tab.path}
                isActive={tab.id === activeTabId}
                onSelect={select}
              />
            ) : (
              <RailItem
                label={tab.label}
                icon={TAB_ICONS[tab.id]}
                href={tab.path}
                isActive={tab.id === activeTabId}
                onSelect={select}
              />
            )}
          </div>
        );
      })}
    </Rail>
  );
}
